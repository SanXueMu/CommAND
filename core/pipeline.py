"""L5 线性管线状态机：上步结果 → 下步输入的纯函数（S3 实现）。

变量模板仅三种：{{ input.* }} / {{ prev }} / {{ step[n].output }}——够用且无法图灵化。
"""

from typing import Any


def resolve_input(step: dict[str, Any], pipeline_input: dict[str, Any], prev_output: Any, history: dict[int, Any]) -> dict[str, Any]:
    raise NotImplementedError("S3 里程碑实现")
