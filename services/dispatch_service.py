"""L4 派发编排：提交（信封校验→入队）/ 跟踪 / 取消（S2 实现）。"""

from typing import Any

from store.db import Db
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo


class DispatchService:
    """任务提交与 handle 生命周期驱动；信封校验失败即 422 拒绝不入队。"""

    def __init__(self, db: Db, task_repo: TaskRepo, tool_repo: ToolRepo) -> None:
        self._db = db
        self._task_repo = task_repo
        self._tool_repo = tool_repo

    def submit(self, tool_id: str, input: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("S2 里程碑实现")
