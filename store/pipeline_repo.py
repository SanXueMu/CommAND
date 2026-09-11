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
                          input_schema: dict[str, Any] | None = None) -> None:
        """注册/更新流定义；type 不可变（变更由 service 层拒绝），input_schema 缺省保留旧值。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pipelines (id, name, steps, doc_md, type, input_schema)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, steps = EXCLUDED.steps, doc_md = EXCLUDED.doc_md,
                    input_schema = COALESCE(EXCLUDED.input_schema, pipelines.input_schema),
                    created_at = now()
                """,
                (pipeline_id, name, Json(steps), doc_md, ptype,
                 Json(input_schema) if input_schema is not None else None),
            )

    def get_definition(self, pipeline_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, name, steps, doc_md, created_at, type, input_schema FROM pipelines WHERE id = %s",
                (pipeline_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "steps": row[2], "doc_md": row[3],
                "created_at": row[4], "type": row[5] or "flow", "input_schema": row[6]}

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

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50,
                  offset: int = 0) -> list[dict[str, Any]]:
        """运行列表（job 粒度，按创建时间倒序）——translee 任务列表体验。"""
        sql = ("SELECT id, pipeline_id, input, status, error, progress, created_at, finished_at "
               "FROM pipeline_runs")
        params: list[Any] = []
        if pipeline_id:
            sql += " WHERE pipeline_id = %s"
            params.append(pipeline_id)
        sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params += [limit, offset]
        with self._db.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"id": r[0], "pipeline_id": r[1], "input": r[2], "status": r[3], "error": r[4],
             "progress": r[5], "created_at": r[6], "finished_at": r[7]}
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
        """删除 run：先解绑其任务（保留任务历史），再删 run（子 run 一并删）。"""
        with self._db.pool.connection() as conn:
            with conn.transaction():
                conn.execute("UPDATE tasks SET pipeline_run = NULL WHERE pipeline_run = %s", (run_id,))
                conn.execute("DELETE FROM pipeline_runs WHERE parent_run_id = %s", (run_id,))
                conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (run_id,))

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
                   parent_step_index: int | None = None) -> str:
        """创建 run；parent 两列非空即子 run（008 唯一索引保证同父步活跃子 run 唯一）。"""
        run_id = "p_" + secrets.token_hex(8)
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs (id, pipeline_id, input, parent_run_id, parent_step_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, pipeline_id, Json(input), parent_run_id, parent_step_index),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.pipeline_id, r.input, r.status, r.error, r.progress,
                       r.created_at, r.finished_at, r.parent_run_id, r.parent_step_index
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
        }

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
