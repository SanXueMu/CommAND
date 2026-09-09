"""L3 请求/响应模型：信封与任务驱动端点的出入参。"""

from typing import Any

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    """调用信封：自包含，无任何隐式状态。"""

    tool: str
    input: dict[str, Any] = Field(default_factory=dict)


class TaskAccepted(BaseModel):
    handle: str
    status: str = "queued"


class TaskOutput(BaseModel):
    result: dict[str, Any]
