"""L6 pipelines / pipeline_runs 表仓储：定义读写与运行实体。"""

import secrets
from typing import Any

from psycopg.types.json import Json

from store.db import Db


class PipelineRepo:
    """管线定义 upsert；运行实体创建/推进/收口；按 run 汇总已完成输出。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def upsert_definition(self, pipeline_id: str, name: str, steps: list[dict[str, Any]], doc_md: str | None = None) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pipelines (id, name, steps, doc_md) VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, steps = EXCLUDED.steps, doc_md = EXCLUDED.doc_md, created_at = now()
                """,
                (pipeline_id, name, Json(steps), doc_md),
            )

    def get_definition(self, pipeline_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, name, steps, doc_md, created_at FROM pipelines WHERE id = %s",
                (pipeline_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "steps": row[2], "doc_md": row[3], "created_at": row[4]}

    def list_definitions(self) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, steps, created_at FROM pipelines ORDER BY id"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "steps": r[2], "created_at": r[3]} for r in rows
        ]

    def create_run(self, pipeline_id: str, input: dict[str, Any]) -> str:
        run_id = "p_" + secrets.token_hex(8)
        with self._db.pool.connection() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (id, pipeline_id, input) VALUES (%s, %s, %s)",
                (run_id, pipeline_id, Json(input)),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.pipeline_id, r.input, r.status, r.error, r.created_at, r.finished_at
                FROM pipeline_runs r WHERE r.id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0], "pipeline_id": row[1], "input": row[2], "status": row[3],
            "error": row[4], "created_at": row[5], "finished_at": row[6],
        }

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
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT step_index, output FROM tasks
                WHERE pipeline_run = %s AND status = 'succeeded'
                ORDER BY step_index
                """,
                (run_id,),
            ).fetchall()
        return {r[0]: r[1] for r in rows}
