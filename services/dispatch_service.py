"""L4 派发编排：提交（信封校验→入队）/ 跟踪 / 列表 / 取消。"""

from typing import Any

from core.errors import (
    TaskConflictError,
    TaskNotFoundError,
    ToolNotFoundError,
)
from core.protocol import validate_payload
from store.db import Db
from store.event_repo import EventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

TERMINAL = {"succeeded", "failed", "failed_review", "cancelled", "interrupted"}


class DispatchService:
    """任务提交与 handle 生命周期驱动；信封校验失败即拒绝不入队。"""

    def __init__(
        self,
        db: Db,
        task_repo: TaskRepo,
        tool_repo: ToolRepo,
        event_repo: EventRepo,
        scheduler: Any | None = None,
    ) -> None:
        self._db = db
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._event_repo = event_repo
        self._scheduler = scheduler

    def submit(
        self,
        tool_id: str,
        input: dict[str, Any],
        pipeline_run: str | None = None,
        step_index: int = 0,
    ) -> dict[str, Any]:
        tool = self._tool_repo.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"工具未注册或不活跃: {tool_id}")
        validate_payload(tool["manifest"]["io"]["input_schema"], input, kind="input")
        max_attempts = tool["manifest"]["resources"].get("max_attempts", 1)
        handle = self._task_repo.enqueue(
            tool_id, input, max_attempts=max_attempts,
            pipeline_run=pipeline_run, step_index=step_index,
        )
        return {"handle": handle, "status": "queued"}

    def get(self, handle: str) -> dict[str, Any]:
        task = self._task_repo.get(handle)
        if task is None:
            raise TaskNotFoundError(f"任务不存在: {handle}")
        return task

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._task_repo.list(status=status, limit=limit)

    def cancel(self, handle: str) -> dict[str, Any]:
        task = self.get(handle)
        if task["status"] in TERMINAL:
            raise TaskConflictError(f"任务已终态 {task['status']}，不可取消")
        if task["status"] == "queued":
            self._task_repo.cancel_queued(handle)
            return {"handle": handle, "status": "cancelled"}
        if self._scheduler is not None and self._scheduler.request_cancel(handle):
            return {"handle": handle, "status": "cancelling"}
        raise TaskConflictError("运行中任务不在本调度器管理内，无法取消")
