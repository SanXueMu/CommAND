"""L5 管线模板解析：三变量（input / prev / step[n].output），刻意不可图灵化。

语义：
- 整串引用（值即模板串）→ 原类型传值（数组/对象/数字不降级为字符串）
- 字符串内嵌引用 → 插值为 str
- 引用不存在 → ToolUserError（管线定义错误归用户侧）
"""

import re
from typing import Any

from core.errors import ToolUserError

_REF = re.compile(
    r"^\{\{\s*(input|prev|step\[(\d+)\]\.output)((?:\.[A-Za-z0-9_\u4e00-\u9fff-]+)*)\s*\}\}$"
)
_EMBEDDED = re.compile(r"\{\{\s*(input|prev|step\[\d+\]\.output)(?:\.[A-Za-z0-9_\u4e00-\u9fff-]+)*\s*\}\}")


def _lookup(root: Any, segments: list[str], ref: str) -> Any:
    node = root
    for segment in segments:
        if isinstance(node, dict) and segment in node:
            node = node[segment]
        elif isinstance(node, list) and segment.isdigit() and int(segment) < len(node):
            node = node[int(segment)]
        else:
            raise ToolUserError(f"管线模板引用不存在: {ref}")
    return node


def resolve_input(
    step_input: Any,
    pipeline_input: dict[str, Any],
    prev_output: Any,
    history: dict[int, Any],
) -> dict[str, Any]:
    """解析单步 input 模板；history 为 {step_index: output} 已完成历史。"""

    def resolve_value(value: Any) -> Any:
        if isinstance(value, str):
            full = _REF.match(value)
            if full:
                return _resolve_ref(full, pipeline_input, prev_output, history, value)
            return _EMBEDDED.sub(
                lambda m: str(_resolve_ref_ref_only(m, pipeline_input, prev_output, history)),
                value,
            )
        if isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve_value(item) for item in value]
        return value

    return {k: resolve_value(v) for k, v in step_input.items()}


def _resolve_ref(match: re.Match, pipeline_input, prev_output, history, original: str) -> Any:
    source, step_idx, path = match.group(1), match.group(2), match.group(3)
    segments = [s for s in path.split(".") if s]
    if source == "input":
        return _lookup(pipeline_input, segments, original)
    if source == "prev":
        return _lookup(prev_output, segments, original)
    return _lookup(history.get(int(step_idx), {}), segments, original)


def _resolve_ref_ref_only(match: re.Match, pipeline_input, prev_output, history) -> Any:
    full = _REF.match(match.group(0))
    if full is None:
        raise ToolUserError(f"管线模板不合法: {match.group(0)}")
    return _resolve_ref(full, pipeline_input, prev_output, history, match.group(0))
