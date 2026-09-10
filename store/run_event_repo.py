"""L6 run_events 表仓储：流级审计轨迹（append-only，工单的审批记录）。"""

from typing import Any

from psycopg.types.json import Json

from store.db import Db

AUDIT_KINDS = {
    "created", "step_queued", "step_started",
    "step_completed", "step_failed", "step_cancelled", "step_skipped",
    "pause_requested", "paused_at_boundary",
    "resume_requested", "resumed",
    "abort_requested", "run_aborted", "step_abort",
    "rerun_requested", "step_rerun", "flow_rerun",
    "override_applied",
    "subrun_created", "subrun_finished",
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

    def skipped_steps(self, run_id: str) -> set[int]:
        """D2：曾被 when 跳过的步骤集合（resume 重放时识别，避免把 skipped 当未到）。"""
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT detail->>'step_index' FROM run_events "
                "WHERE run_id = %s AND kind = 'step_skipped'",
                (run_id,),
            ).fetchall()
        return {int(r[0]) for r in rows}

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
