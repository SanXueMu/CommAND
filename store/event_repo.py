"""L6 task_events 表仓储：append-only 事件流与查询（S2 实现）。"""

from typing import Any

from store.db import Db


class EventRepo:
    """事件是不可变历史：只追加、按 handle 查询、随任务删除级联净。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def append(self, handle: str, type: str, data: dict[str, Any]) -> None:
        raise NotImplementedError("S2 里程碑实现")

    def list_by_handle(self, handle: str) -> list[dict[str, Any]]:
        return []
