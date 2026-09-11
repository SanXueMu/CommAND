"""L6 tasks 表仓储：认领（FOR UPDATE SKIP LOCKED）/ 并发闸 / 心跳 / 恢复 / 终态落盘。"""

from __future__ import annotations

import secrets
from typing import Any

from psycopg.types.json import Json

from store.db import Db

_COLUMNS = (
    "handle, tool_id, status, input, output, error, pipeline_run, step_index, "
    "attempt, max_attempts, created_at, started_at, finished_at"
)


class TaskRepo:
    """队列 SQL 唯一归属：多 worker 无争抢单语句原子认领。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def enqueue(
        self,
        tool_id: str,
        input: dict[str, Any],
        max_attempts: int = 1,
        pipeline_run: str | None = None,
        step_index: int = 0,
    ) -> str:
        handle = "t_" + secrets.token_hex(8)
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (handle, tool_id, Json(input), max_attempts, pipeline_run, step_index),
            )
        return handle

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        """认领一条排队任务：按入队顺序，同工具 running 数受 manifest 并发闸约束。"""
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                WITH candidate AS (
                    SELECT t.handle
                    FROM tasks t
                    JOIN tools tl ON tl.id = t.tool_id
                    WHERE t.status = 'queued'
                      AND (SELECT count(*) FROM tasks r
                           WHERE r.tool_id = t.tool_id AND r.status = 'running')
                          < (tl.manifest->'resources'->>'concurrency')::int
                    ORDER BY t.created_at
                    FOR UPDATE OF t SKIP LOCKED
                    LIMIT 1
                )
                UPDATE tasks SET status = 'running', claimed_by = %s,
                       started_at = now(), heartbeat_at = now()
                WHERE handle IN (SELECT handle FROM candidate)
                RETURNING handle, tool_id, input, attempt, max_attempts, pipeline_run, step_index
                """,
                (worker_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "handle": row[0],
            "tool_id": row[1],
            "input": row[2],
            "attempt": row[3],
            "max_attempts": row[4],
            "pipeline_run": row[5],
            "step_index": row[6],
        }

    def heartbeat(self, handle: str) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                "UPDATE tasks SET heartbeat_at = now() WHERE handle = %s AND status = 'running'",
                (handle,),
            )

    def requeue(self, handle: str) -> None:
        """心跳过期或领域错误可重试：attempt+1 回队。"""
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                UPDATE tasks SET status = 'queued', attempt = attempt + 1,
                       claimed_by = NULL, started_at = NULL, heartbeat_at = NULL
                WHERE handle = %s AND status = 'running'
                """,
                (handle,),
            )

    def finish(
        self,
        handle: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                UPDATE tasks SET status = %s, output = %s, error = %s,
                       finished_at = now(), claimed_by = NULL, heartbeat_at = NULL
                WHERE handle = %s
                """,
                (status, Json(output) if output is not None else None,
                 Json(error) if error is not None else None, handle),
            )

    def cancel_queued(self, handle: str) -> bool:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE tasks SET status = 'cancelled', finished_at = now()
                WHERE handle = %s AND status = 'queued'
                RETURNING handle
                """,
                (handle,),
            ).fetchone()
        return row is not None

    def recover_stale(self, timeout_s: int) -> dict[str, int]:
        """心跳过期的 running 任务：可重试回队（attempt+1），不可重试标记 interrupted。"""
        requeued = interrupted = 0
        with self._db.pool.connection() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT handle, attempt, max_attempts FROM tasks
                    WHERE status = 'running'
                      AND heartbeat_at < now() - make_interval(secs => %s)
                    FOR UPDATE SKIP LOCKED
                    """,
                    (timeout_s,),
                ).fetchall()
                for handle, attempt, max_attempts in rows:
                    if attempt < max_attempts:
                        conn.execute(
                            """
                            UPDATE tasks SET status = 'queued', attempt = attempt + 1,
                                   claimed_by = NULL, started_at = NULL, heartbeat_at = NULL
                            WHERE handle = %s
                            """,
                            (handle,),
                        )
                        requeued += 1
                    else:
                        conn.execute(
                            """
                            UPDATE tasks SET status = 'interrupted', finished_at = now(),
                                   claimed_by = NULL, heartbeat_at = NULL,
                                   error = COALESCE(error, %s::jsonb)
                            WHERE handle = %s
                            """,
                            (Json({"kind": "system", "code": "heartbeat_timeout",
                                   "message": "心跳过期且不可重试"}), handle),
                        )
                        interrupted += 1
        return {"requeued": requeued, "interrupted": interrupted}

    def get(self, handle: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE handle = %s", (handle,)
            ).fetchone()
        return self._to_view(row) if row else None

    def list(self, status: str | None = None, limit: int = 50,
             kind: str | None = None, offset: int = 0,
             q: str | None = None) -> dict[str, Any]:
        """任务列表。C4 归类：pipeline_run 上溯根 run（限深两层）join pipeline.type
        → kind ∈ tool/flow/workflow；root_run_id/root_pipeline_id 供下钻。
        富化：join tools/pipelines 中文名（tool_name/pipeline_name）；offset/q 分页检索，
        返回 {tasks, total}。"""
        sql = """
            SELECT t.handle, t.tool_id, t.status, t.input, t.output, t.error,
                   t.pipeline_run, t.step_index, t.attempt, t.max_attempts,
                   t.created_at, t.started_at, t.finished_at,
                   r.id, r.parent_run_id, pr.id,
                   COALESCE(p2.id, p1.id), COALESCE(p2.type, p1.type),
                   tl.name, COALESCE(p2.name, p1.name)
            FROM tasks t
            LEFT JOIN pipeline_runs r ON r.id = t.pipeline_run
            LEFT JOIN pipeline_runs pr ON pr.id = r.parent_run_id
            LEFT JOIN pipelines p1 ON p1.id = r.pipeline_id
            LEFT JOIN pipelines p2 ON p2.id = pr.pipeline_id
            LEFT JOIN tools tl ON tl.id = t.tool_id
        """
        conds: list[str] = []
        params: list[Any] = []
        if status is not None:
            conds.append("t.status = %s")
            params.append(status)
        if kind == "tool":
            conds.append("t.pipeline_run IS NULL")
        elif kind == "flow":
            conds.append(
                "t.pipeline_run IS NOT NULL AND r.parent_run_id IS NULL "
                "AND COALESCE(p1.type, 'flow') = 'flow'")
        elif kind == "workflow":
            conds.append("r.parent_run_id IS NOT NULL OR COALESCE(p1.type, 'flow') = 'workflow'")
        elif kind is not None:
            raise ValueError(f"kind 仅支持 tool/flow/workflow: {kind}")
        if q:
            like = f"%{q}%"
            conds.append("(tl.name ILIKE %s OR t.handle ILIKE %s OR COALESCE(p2.name, p1.name) ILIKE %s)")
            params.extend([like, like, like])
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        with self._db.pool.connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM (" + sql.replace(" ORDER BY t.created_at DESC LIMIT %s", "") + ") _c",
                tuple(params),
            ).fetchone()[0]
            sql += " ORDER BY t.created_at DESC LIMIT %s OFFSET %s"
            rows = conn.execute(sql, tuple(params + [limit, offset])).fetchall()
        views = []
        for row in rows:
            view = self._to_view(row[:13])
            run_id, parent_run_id, parent_parent_id, root_pid, root_type, tool_name, pipeline_name = row[13:]
            if run_id is None:
                view["task_kind"] = "tool"
            elif parent_run_id is None:
                view["task_kind"] = root_type or "flow"  # 根 run 直属任务：flow/workflow
            else:
                view["task_kind"] = "workflow"  # 子 run 任务：根必为 workflow（限深两层）
            view["root_run_id"] = parent_parent_id or run_id
            view["root_pipeline_id"] = root_pid
            if tool_name:
                view["tool_name"] = tool_name
            if pipeline_name:
                view["pipeline_name"] = pipeline_name
            views.append(view)
        return {"tasks": views, "total": total}

    def stats_by_tool(self, tool_id: str) -> dict[str, Any]:
        """量化性能（工具详情「量化性能」数据源）：执行次数/成功率/平均耗时。
        成功率与耗时只按终态任务计算，运行中不参与分母。"""
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE status IN ('succeeded','failed',
                                                         'failed_review','cancelled','interrupted')),
                       COUNT(*) FILTER (WHERE status = 'succeeded'),
                       AVG(EXTRACT(EPOCH FROM (finished_at - started_at)))
                           FILTER (WHERE status = 'succeeded'
                                   AND started_at IS NOT NULL AND finished_at IS NOT NULL)
                FROM tasks WHERE tool_id = %s
                """,
                (tool_id,),
            ).fetchone()
        total, done, ok, avg_seconds = row
        return {
            "executions": total,
            "success_rate": round(ok / done, 4) if done else None,
            "avg_seconds": round(avg_seconds, 1) if avg_seconds is not None else None,
        }

    def stats_by_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        """流维度的量化性能：按根管线归集（任务→run→根 run 的管线）。"""
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE t.status IN ('succeeded','failed',
                                                           'failed_review','cancelled','interrupted')),
                       COUNT(*) FILTER (WHERE t.status = 'succeeded'),
                       AVG(EXTRACT(EPOCH FROM (t.finished_at - t.started_at)))
                           FILTER (WHERE t.status = 'succeeded'
                                   AND t.started_at IS NOT NULL AND t.finished_at IS NOT NULL)
                FROM tasks t
                LEFT JOIN pipeline_runs r ON r.id = t.pipeline_run
                LEFT JOIN pipeline_runs pr ON pr.id = r.parent_run_id
                LEFT JOIN pipelines p1 ON p1.id = r.pipeline_id
                LEFT JOIN pipelines p2 ON p2.id = pr.pipeline_id
                WHERE COALESCE(p2.id, p1.id) = %s
                """,
                (pipeline_id,),
            ).fetchone()
        total, done, ok, avg_seconds = row
        return {
            "executions": total,
            "success_rate": round(ok / done, 4) if done else None,
            "avg_seconds": round(avg_seconds, 1) if avg_seconds is not None else None,
        }

    def list_by_pipeline_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE pipeline_run = %s ORDER BY step_index",
                (run_id,),
            ).fetchall()
        return [self._to_view(row) for row in rows]

    @staticmethod
    def _to_view(row: tuple) -> dict[str, Any]:
        return {
            "handle": row[0],
            "tool_id": row[1],
            "status": row[2],
            "input": row[3],
            "output": row[4],
            "error": row[5],
            "pipeline_run": row[6],
            "step_index": row[7],
            "attempt": row[8],
            "max_attempts": row[9],
            "created_at": row[10],
            "started_at": row[11],
            "finished_at": row[12],
        }
