"""L6 tasks 表仓储：认领（FOR UPDATE SKIP LOCKED）/ 并发闸 / 心跳 / 恢复 / 终态落盘。"""

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
                RETURNING handle, tool_id, input, attempt, max_attempts
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

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = f"SELECT {_COLUMNS} FROM tasks"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = %s"
            params = (status,)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params = params + (limit,)
        with self._db.pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
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
