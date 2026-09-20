"""L6 pipelines / pipeline_runs 表仓储：定义读写与运行实体。"""

import secrets
from typing import Any

from psycopg.types.json import Json

from store.db import Db


class PipelineRepo:
    """管线定义 upsert；运行实体创建/推进/收口；按 run 汇总已完成输出。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert_definition(self, pipeline_id: str, name: str, steps: list[dict[str, Any]],
                          doc_md: str | None = None, ptype: str = "flow",
                          input_schema: dict[str, Any] | None = None,
                          on_failure: dict[str, Any] | None = None) -> None:
        """注册/更新流定义；type 不可变（变更由 service 层拒绝），input_schema/on_failure 缺省保留旧值。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pipelines (id, name, steps, doc_md, type, input_schema, on_failure)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, steps = EXCLUDED.steps, doc_md = EXCLUDED.doc_md,
                    input_schema = COALESCE(EXCLUDED.input_schema, pipelines.input_schema),
                    on_failure = COALESCE(EXCLUDED.on_failure, pipelines.on_failure),
                    created_at = now()
                """,
                (pipeline_id, name, Json(steps), doc_md, ptype,
                 Json(input_schema) if input_schema is not None else None,
                 Json(on_failure) if on_failure is not None else None),
            )

    def get_definition(self, pipeline_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, name, steps, doc_md, created_at, type, input_schema, on_failure "
                "FROM pipelines WHERE id = %s",
                (pipeline_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "steps": row[2], "doc_md": row[3],
                "created_at": row[4], "type": row[5] or "flow", "input_schema": row[6],
                "on_failure": row[7]}

    def list_definitions(self) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, steps, created_at, type, input_schema FROM pipelines ORDER BY id"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "steps": r[2], "created_at": r[3],
             "type": r[4] or "flow", "input_schema": r[5]} for r in rows
        ]

    def count_active_runs(self, pipeline_id: str) -> int:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT count(*) FROM pipeline_runs WHERE pipeline_id = %s AND status IN ('running','paused')",
                (pipeline_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def batch_ids_of_flows(self, flow_ids: list[str]) -> set[str]:
        """至少有一条 run 属于给定流域的批次 id 集合（X2：批次下拉按工作台域隔离）。"""
        if not flow_ids:
            return set()
        sql = ("SELECT DISTINCT batch_id FROM pipeline_runs "
               "WHERE batch_id IS NOT NULL AND pipeline_id = ANY(%s)")
        with self._db.pool.connection() as conn:
            rows = conn.execute(sql, (flow_ids,)).fetchall()
        return {r[0] for r in rows}

    def best_runs_by_batch(self, batch_id: str) -> list[dict[str, Any]]:
        """批次内**每个文件的最优 run**（成功优先 > 暂停/跳过 > 其它，同级取最新）。

        用 `DISTINCT ON (input->>'file')` 一条 SQL 完成，**不受 limit 窗口限制**。
        为什么必须这样：批次 run 数会远大于任何分页上限（线上 341 条），而 `list_runs`
        只取最新 N 条 → 更早的**成功 run 被挤出窗口**，导出只能放回源文件（用户看到
        「导出全是没翻译的」2026-09-14）。
        """
        sql = """
            SELECT DISTINCT ON (COALESCE(input->>'file', id))
                   id, pipeline_id, input, status, error, progress, created_at, finished_at,
                   batch_id, fallback_of
            FROM pipeline_runs
            WHERE batch_id = %s
            ORDER BY COALESCE(input->>'file', id),
                     CASE status WHEN 'succeeded' THEN 0
                                 WHEN 'paused' THEN 1
                                 WHEN 'skipped' THEN 1
                                 ELSE 2 END,
                     created_at DESC
        """
        with self._db.pool.connection() as conn:
            rows = conn.execute(sql, (batch_id,)).fetchall()
        return [
            {"id": r[0], "pipeline_id": r[1], "input": r[2], "status": r[3], "error": r[4],
             "progress": r[5], "created_at": r[6], "finished_at": r[7], "batch_id": r[8],
             "fallback_of": r[9]}
            for r in rows
        ]

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50,
                  offset: int = 0, batch_id: str | None = None) -> list[dict[str, Any]]:
        """运行列表（job 粒度，按创建时间倒序）——translee 任务列表体验。"""
        sql = ("SELECT id, pipeline_id, input, status, error, progress, created_at, finished_at, "
               "batch_id, fallback_of FROM pipeline_runs")
        clauses: list[str] = []
        params: list[Any] = []
        if pipeline_id:
            clauses.append("pipeline_id = %s")
            params.append(pipeline_id)
        if batch_id:
            clauses.append("batch_id = %s")
            params.append(batch_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params += [limit, offset]
        with self._db.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"id": r[0], "pipeline_id": r[1], "input": r[2], "status": r[3], "error": r[4],
             "progress": r[5], "created_at": r[6], "finished_at": r[7], "batch_id": r[8],
             "fallback_of": r[9]}
            for r in rows
        ]

    def count_runs(self, pipeline_id: str | None = None) -> int:
        sql = "SELECT count(*) FROM pipeline_runs"
        params: list[Any] = []
        if pipeline_id:
            sql += " WHERE pipeline_id = %s"
            params.append(pipeline_id)
        with self._db.pool.connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    def delete_run(self, run_id: str) -> None:
        """删除 run（含子 run 整棵树、审计事件），解绑整棵子树的 tasks（保留任务历史）。

        run_events.run_id 在 006 里是无级联外键（NO ACTION），不先清事件会
        ForeignKeyViolation → 500（011 迁移已改 CASCADE，此处仍显式清理以防旧库未迁移）；
        pipeline_runs.parent_run_id 同为无级联 self-FK，故按深度降序先子后父删除。
        """
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE tree(id, depth) AS (
                    SELECT id, 0 FROM pipeline_runs WHERE id = %s
                    UNION ALL
                    SELECT p.id, t.depth + 1
                    FROM pipeline_runs p JOIN tree t ON p.parent_run_id = t.id
                )
                SELECT id FROM tree ORDER BY depth DESC
                """,
                (run_id,),
            ).fetchall()
            ids = [row[0] for row in rows]
            with conn.transaction():
                conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (ids,))
                conn.execute("UPDATE tasks SET pipeline_run = NULL WHERE pipeline_run = ANY(%s)",
                             (ids,))
                for rid in ids:
                    conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))

    def delete_definition(self, pipeline_id: str) -> None:
        with self._db.pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    "UPDATE pipeline_runs SET pipeline_id = NULL WHERE pipeline_id = %s",
                    (pipeline_id,),
                )
                conn.execute("DELETE FROM pipelines WHERE id = %s", (pipeline_id,))

    def create_run(self, pipeline_id: str, input: dict[str, Any],
                   parent_run_id: str | None = None,
                   parent_step_index: int | None = None,
                   batch_id: str | None = None,
                   fallback_of: str | None = None) -> str:
        """创建 run；parent 两列非空即子 run（008 唯一索引保证同父步活跃子 run 唯一）。

        fallback_of 非空表示这条 run 是「因原 run 能力不可用而自动降级」产生的（见 015 迁移）。
        """
        run_id = "p_" + secrets.token_hex(8)
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs
                    (id, pipeline_id, input, parent_run_id, parent_step_index, batch_id, fallback_of)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (run_id, pipeline_id, Json(input), parent_run_id, parent_step_index, batch_id,
                 fallback_of),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.pipeline_id, r.input, r.status, r.error, r.progress,
                       r.created_at, r.finished_at, r.parent_run_id, r.parent_step_index,
                       r.batch_id, r.fallback_of
                FROM pipeline_runs r WHERE r.id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0], "pipeline_id": row[1], "input": row[2], "status": row[3],
            "error": row[4], "progress": row[5], "created_at": row[6], "finished_at": row[7],
            "parent_run_id": row[8], "parent_step_index": row[9],
            "batch_id": row[10], "fallback_of": row[11],
        }

    def update_run_input(self, run_id: str, input: dict[str, Any]) -> bool:
        """就地更新 run 的 input（替换原件 / 修正密钥名等参数后继续）——仅非运行中调用。"""
        with self._db.pool.connection() as conn:
            cursor = conn.execute("UPDATE pipeline_runs SET input = %s WHERE id = %s",
                                  (Json(input), run_id))
        return cursor.rowcount > 0

    def cas_run_status(self, run_id: str, from_statuses: tuple[str, ...], to_status: str) -> bool:
        """原子状态迁移（乐观 CAS）：from_statuses 内才迁移，返回是否成功。"""
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE pipeline_runs SET status = %s,
                    finished_at = CASE WHEN %s IN ('succeeded','failed','failed_review','cancelled','interrupted')
                                       THEN now() ELSE finished_at END
                WHERE id = %s AND status = ANY(%s)
                RETURNING id
                """,
                (to_status, to_status, run_id, list(from_statuses)),
            ).fetchone()
        return row is not None

    def set_run_progress(self, run_id: str, next_index: int) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET progress = %s WHERE id = %s",
                (next_index, run_id),
            )

    def finish_run_forced(self, run_id: str, status: str, error: dict[str, Any] | None = None) -> None:
        """强制收口（不受 running 前置约束）：abort 等人工操作用。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs SET status = %s, error = %s, finished_at = now()
                WHERE id = %s AND status NOT IN ('succeeded','cancelled','interrupted','failed','failed_review')
                """,
                (status, Json(error) if error is not None else None, run_id),
            )

    def latest_task_by_step(self, run_id: str) -> dict[int, dict[str, Any]]:
        """每步最新任务（rerun 后同步多任务时以最新为准）。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (step_index)
                    step_index, handle, status, attempt, input, output
                FROM tasks WHERE pipeline_run = %s
                ORDER BY step_index, created_at DESC
                """,
                (run_id,),
            ).fetchall()
        return {r[0]: {"step_index": r[0], "handle": r[1], "status": r[2], "attempt": r[3],
                       "input": r[4], "output": r[5]} for r in rows}

    def active_task_handles(self, run_id: str) -> list[str]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT handle FROM tasks WHERE pipeline_run = %s AND status IN ('queued','running')",
                (run_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def finish_run(
        self, run_id: str, status: str, error: dict[str, Any] | None = None
    ) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs SET status = %s, error = %s, finished_at = now()
                WHERE id = %s AND status = 'running'
                """,
                (status, Json(error) if error is not None else None, run_id),
            )

    _LIGHT_OUTPUT_COLS = """
               {p}->>'path' AS path, {p}->>'name' AS name,
               {p}->>'layered_file' AS layered_file, {p}->>'layered_name' AS layered_name,
               {p}->'usage' AS usage, {p}->'usage_by_model' AS usage_by_model,
               ({p}->>'calls')::int AS calls, ({p}->>'cache_hits')::int AS cache_hits,
               CASE WHEN jsonb_typeof({p}->'statuses') = 'array'
                    THEN jsonb_array_length({p}->'statuses') END AS statuses_len,
               CASE WHEN jsonb_typeof({p}->'statuses') = 'array'
                    THEN (SELECT count(*) FROM jsonb_array_elements_text({p}->'statuses') e
                          WHERE e = 'review') END AS review_count_arr,
               {p}->>'review_count' AS review_count_key,
               CASE WHEN jsonb_typeof({p}->'failed_pages') = 'array'
                    THEN jsonb_array_length({p}->'failed_pages') END AS failed_pages_count,
               ({p}->>'records_count')::int AS records_count,
               CASE WHEN jsonb_typeof({p}->'review_notes') = 'array'
                    THEN jsonb_array_length({p}->'review_notes') END AS review_notes_count
    """

    def light_step_statuses(self, run_ids: list[str]) -> dict[str, dict[int, str]]:
        """每 run 每步**最新任务的状态**（不取任何载荷）——steps_done 计数用。"""
        if not run_ids:
            return {}
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (pipeline_run, step_index) pipeline_run, step_index, status
                FROM tasks WHERE pipeline_run = ANY(%s)
                ORDER BY pipeline_run, step_index, created_at DESC
                """,
                (list(run_ids),),
            ).fetchall()
        out: dict[str, dict[int, str]] = {}
        for run_id, idx, status in rows:
            out.setdefault(run_id, {})[idx] = status
        return out

    def light_step_outputs(self, run_ids: list[str]) -> dict[str, dict[int, dict[str, Any]]]:
        """每 run 每步最新成功任务的**精简输出**：只投影产物路径/名称与用量计数。

        绝不传输 `translations`/`segments`/`statuses` 等大数组（列表接口曾因此达数十 MB/次）。
        C1：父 run 无任务的 pipeline 步，补该步子 run 末步成功任务的精简输出（仅补缺不覆盖）。
        """
        if not run_ids:
            return {}
        cols = self._LIGHT_OUTPUT_COLS
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT ON (pipeline_run, step_index) pipeline_run, step_index, {cols.format(p="output")}
                FROM tasks WHERE pipeline_run = ANY(%s) AND status = 'succeeded'
                ORDER BY pipeline_run, step_index, created_at DESC
                """,
                (list(run_ids),),
            ).fetchall()
            sub_rows = conn.execute(
                f"""
                SELECT DISTINCT ON (r.parent_run_id, r.parent_step_index)
                       r.parent_run_id, r.parent_step_index, {cols.format(p="t.output")}
                FROM pipeline_runs r
                JOIN tasks t ON t.pipeline_run = r.id AND t.status = 'succeeded'
                WHERE r.parent_run_id = ANY(%s) AND r.status = 'succeeded'
                ORDER BY r.parent_run_id, r.parent_step_index, t.created_at DESC
                """,
                (list(run_ids),),
            ).fetchall()
        out: dict[str, dict[int, dict[str, Any]]] = {}
        for run_id, idx, *rest in rows:
            out.setdefault(run_id, {})[idx] = self._light_output(rest)
        for run_id, idx, *rest in sub_rows:  # 子输出仅补缺，不覆盖父 run 本地任务
            out.setdefault(run_id, {}).setdefault(idx, self._light_output(rest))
        return out

    @staticmethod
    def _light_output(values: list[Any]) -> dict[str, Any]:
        path, name, layered_file, layered_name, usage, usage_by_model, calls, cache_hits, \
            statuses_len, review_count_arr, review_count_key, failed_pages_count, records_count, review_notes_count = values
        return {
            "path": path, "name": name, "layered_file": layered_file, "layered_name": layered_name,
            "usage": usage, "usage_by_model": usage_by_model, "calls": calls, "cache_hits": cache_hits,
            "statuses_len": statuses_len,
            "failed_pages": failed_pages_count,
            "records_count": records_count,
            "review_notes_count": review_notes_count,
            "review_count": review_count_arr if review_count_arr is not None else (int(review_count_key) if review_count_key not in (None, "") else None),
        }

    def steps_total_by_pipeline(self, pipeline_ids: list[str]) -> dict[str, int]:
        """批量取管线步数（供列表 x/n 的 n）——一条查询替代逐 run 取定义。"""
        ids = [pid for pid in dict.fromkeys(pipeline_ids) if pid]
        if not ids:
            return {}
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, jsonb_array_length(steps) FROM pipelines WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def db_referenced_outside(self, db_path: str, tree_ids: list[str]) -> bool:
        """AD1：该库路径是否还被树外 run 的任务输出引用（LIKE 文本匹配，防误删共享库）。"""
        if not tree_ids:
            return True
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM tasks
                WHERE pipeline_run <> ALL(%s)
                  AND status = 'succeeded'
                  AND output::text LIKE %s
                LIMIT 1
                """,
                (tree_ids, f"%{db_path}%"),
            ).fetchone()
        return row is not None

    def outputs_by_step(self, run_id: str) -> dict[int, Any]:
        """每步最新成功任务的输出（DISTINCT ON 保证 rerun 后取最新成功而非旧任务）。
        C1：pipeline 步在父 run 无任务——其输出取自该步子 run 的末步任务输出。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (step_index) step_index, output FROM tasks
                WHERE pipeline_run = %s AND status = 'succeeded'
                ORDER BY step_index, created_at DESC
                """,
                (run_id,),
            ).fetchall()
            outputs = {r[0]: r[1] for r in rows}
            sub_rows = conn.execute(
                """
                SELECT DISTINCT ON (r.parent_step_index) r.parent_step_index, t.output
                FROM pipeline_runs r
                JOIN tasks t ON t.pipeline_run = r.id AND t.status = 'succeeded'
                WHERE r.parent_run_id = %s AND r.status = 'succeeded'
                ORDER BY r.parent_step_index, t.created_at DESC
                """,
                (run_id,),
            ).fetchall()
        for idx, out in sub_rows:  # 子输出仅补缺，不覆盖本地任务
            outputs.setdefault(idx, out)
        return outputs

    def get_subruns(self, run_id: str) -> dict[int, dict[str, Any]]:
        """该 run 的全部子 run（按父步索引）——resume 重放 / abort 递归 / snapshot 用。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, pipeline_id, parent_step_index, status, created_at, finished_at
                FROM pipeline_runs WHERE parent_run_id = %s
                ORDER BY parent_step_index, created_at
                """,
                (run_id,),
            ).fetchall()
        return {r[2]: {"id": r[0], "pipeline_id": r[1], "parent_step_index": r[2],
                       "status": r[3], "created_at": r[4], "finished_at": r[5]}
                for r in rows}
