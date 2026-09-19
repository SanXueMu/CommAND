"""L6 run_events 表仓储：流级审计轨迹（append-only，工单的审批记录）。"""

from typing import Any

from psycopg.types.json import Json

from store.db import Db

AUDIT_KINDS = {
    "created", "step_queued", "step_started",
    "step_completed", "step_failed", "step_cancelled", "step_skipped", "step_paused",
    "pause_requested", "paused_at_boundary",
    "resume_requested", "resumed",
    "abort_requested", "run_aborted", "step_abort",
    "rerun_requested", "step_rerun", "flow_rerun",
    "override_applied",
    "subrun_created", "subrun_finished",
    "run_fallback",  # 016：能力不可用 → 自动降级到 on_failure.fallback_flow（原/新 run 各一条）
    "file_replaced", "input_updated",  # 017：替换任务原件 / 就地修正任务参数
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

    def skipped_steps_bulk(self, run_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Y1/Y2：批量取每 run 的跳步明细（step_index + when 条件），一条 SQL。"""
        if not run_ids:
            return {}
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT run_id, detail->>'step_index', detail->'when' "
                "FROM run_events WHERE run_id = ANY(%s) AND kind = 'step_skipped'",
                (list(run_ids),),
            ).fetchall()
        out: dict[str, list[dict[str, Any]]] = {}
        for run_id, idx, when in rows:
            out.setdefault(run_id, []).append(
                {"step_index": int(idx), "when": when or {}})
        return out

    def latest_progress_bulk(self, run_ids: list[str]) -> dict[str, str]:
        """AB2：批量取每 run 最新一条工具进度消息（「已识别 12/42 页」），一条 SQL。"""
        if not run_ids:
            return {}
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (run_id) run_id, detail->>'message' "
                "FROM run_events "
                "WHERE run_id = ANY(%s) AND kind = 'progress' "
                "AND detail->>'message' IS NOT NULL "
                "ORDER BY run_id, id DESC",
                (list(run_ids),),
            ).fetchall()
        return {run_id: msg for run_id, msg in rows if msg}

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
