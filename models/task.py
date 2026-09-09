"""任务视图模型：handle 生命周期跨层传递的定型结构。"""

from typing import Any, Literal, TypedDict

TaskStatus = Literal[
    "queued", "running", "succeeded", "failed", "failed_review", "cancelled", "interrupted"
]


class TaskView(TypedDict):
    handle: str
    tool_id: str
    status: TaskStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    attempt: int
    max_attempts: int
