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


_WHEN_KEY = re.compile(r"^(input|prev|step\[(\d+)\]\.output)((?:\.[A-Za-z0-9_\u4e00-\u9fff-]+)+)$")
_EXISTS = "@exists"


def validate_when(when: Any) -> None:
    """D2：when 键格式静态校验（register 时拦截；运行时求值再动态报错）。"""
    if not isinstance(when, dict) or not when:
        raise ToolUserError("when 必须为非空对象")
    for key in when:
        if _WHEN_KEY.match(key) is None:
            raise ToolUserError(f"when 键不合法（须为 input.*/prev.*/step[N].output.* 路径）: {key}")


def evaluate_when(when: dict[str, Any], pipeline_input: dict[str, Any],
                  prev_output: Any, history: dict[int, Any]) -> bool:
    """D2：when 条件求值——所有键值对 AND；值 "@exists" 判存在性，否则等值比较。"""

    def probe(key: str) -> Any:
        m = _WHEN_KEY.match(key)
        if m is None:
            raise ToolUserError(f"when 键不合法: {key}")
        source, step_idx, path = m.group(1), m.group(2), m.group(3)
        segments = [s for s in path.split(".") if s]
        if source == "input":
            root, ref = pipeline_input, key
        elif source == "prev":
            root, ref = prev_output, key
        else:
            root, ref = history.get(int(step_idx)), key
        if root is None:
            raise _Missing
        try:
            return _lookup(root, segments, ref)
        except ToolUserError:
            raise _Missing

    class _Missing(Exception):
        pass

    for key, expected in when.items():
        try:
            actual = probe(key)
        except _Missing:
            if expected == _EXISTS:
                return False
            return False  # 路径不存在 → 条件不成立（不抛，跳步是温和行为）
        if expected == _EXISTS:
            continue
        if actual != expected:
            return False
    return True


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
