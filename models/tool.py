"""工具视图模型：注册表跨层传递的定型结构。"""

from typing import TypedDict


class ToolView(TypedDict):
    id: str
    name: str
    version: str
    description: str
    input_types: list[str]
    output_types: list[str]
    runtime_kind: str
    tags: list[str]
