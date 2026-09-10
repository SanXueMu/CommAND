"""L6 run_events 表仓储：流级审计轨迹（append-only，工单的审批记录）。"""

from typing import Any

from psycopg.types.json import Json

from store.db import Db

AUDIT_KINDS = {
    "created", "step_queued", "step_started",
    "step_completed", "step_failed", "step_cancelled",
    "pause_requested", "paused_at_boundary",
    "resume_requested", "resumed",
    "abort_requested", "run_aborted", "step_abort",
    "rerun_requested", "step_rerun",
    "override_applied",
}


class RunEventRepo:
    def __init__(self, db: Db) -> None:
        self._db = db

    def append(self, run_id: str, task_handle: str | None, kind: str,
               actor: str = "console", detail: dict[str, Any] | None = None) -> None:
        if kind not in AUDIT_KINDS:
            raise ValueError(f"未知审计事件类型: {kind}")
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO run_events (run_id, task_handle, kind, actor, detail)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, task_handle, kind, actor, Json(detail or {})),
            )

    def list(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, task_handle, kind, actor, detail, created_at
                FROM run_events WHERE run_id = %s ORDER BY id DESC LIMIT %s
                """,
                (run_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0], "task_handle": r[1], "kind": r[2], "actor": r[3],
                "detail": r[4], "created_at": r[5],
            }
            for r in rows
        ]
