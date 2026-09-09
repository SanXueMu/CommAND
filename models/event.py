"""事件视图模型：log / progress / artifact / status 四类。"""

from typing import Any, Literal, TypedDict

EventType = Literal["log", "progress", "artifact", "status"]


class EventView(TypedDict):
    type: EventType
    data: dict[str, Any]
