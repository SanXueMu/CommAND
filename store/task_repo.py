"""L6 tasks 表仓储：认领（SKIP LOCKED）/ 心跳 / 恢复 / 终态落盘（S2 实现）。"""

from typing import Any

from store.db import Db


class TaskRepo:
    """队列 SQL 唯一归属：多 worker 无争抢单语句原子认领。"""

    def __init__(self, db: Db) -> None:
        self._db = db

    def enqueue(self, tool_id: str, input: dict[str, Any], max_attempts: int) -> str:
        raise NotImplementedError("S2 里程碑实现")

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("S2 里程碑实现")
