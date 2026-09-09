"""L6 task_events 表仓储：append-only 事件流与增量查询。"""

from typing import Any

from psycopg.types.json import Json

from store.db import Db


class EventRepo:
    """事件是不可变历史：只追加、按 handle 增量查询、随任务删除级联净。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def append(self, handle: str, type: str, data: dict[str, Any]) -> None:
        with self._db.pool.connection() as conn:
            conn.execute(
                "INSERT INTO task_events (handle, type, data) VALUES (%s, %s, %s)",
                (handle, type, Json(data)),
            )

    def list_by_handle(self, handle: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._db.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, type, data, created_at FROM task_events
                WHERE handle = %s AND id > %s ORDER BY id
                """,
                (handle, after_id),
            ).fetchall()
        return [
            {"id": r[0], "type": r[1], "data": r[2], "created_at": r[3]} for r in rows
        ]
