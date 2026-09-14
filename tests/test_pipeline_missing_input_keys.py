"""I1：`input.X` 缺键不再致命（历史 run 重跑 / 降级继承 input 的前提）。

背景（2026-09-14 线上）：重跑回放的是库里**已存**的 input，那批 input 由修复前的旧前端生成、
本就没有 `image_model` 键 → 每次都报「管线模板引用不存在」。降级到版式流同理（它引用 `model`，
图片流的 input 里没有）。故：
- `input.X` 缺失 → 整串引用取 `null`、字符串内嵌取空串（= 用户没填）；
- `prev` / `step[n].output` 仍**严格报错**（流内接线错误必须暴露）。
"""

from __future__ import annotations

import pytest

from core.errors import ToolUserError
from core.pipeline import resolve_input


def test_missing_input_key_resolves_to_none():
    """整串引用：缺键 → None（工具层再按 None 取默认值）。"""
    resolved = resolve_input(
        {"model": "{{ input.image_model }}", "file": "{{ input.file }}"},
        {"file": "/tmp/a.pdf"}, None, {})
    assert resolved == {"model": None, "file": "/tmp/a.pdf"}


def test_missing_input_key_in_embedded_string_resolves_to_empty():
    """字符串内嵌：缺键 → 空串（不能拼出字面量 "None"）。"""
    resolved = resolve_input(
        {"reason": "未处理：{{ input.note }}（请补文字层）"}, {}, None, {})
    assert resolved == {"reason": "未处理：（请补文字层）"}


def test_missing_input_key_with_empty_string_value_is_preserved():
    """用户真的填了空串/None 时按原值传（缺键与显式 null 等价，不报错）。"""
    resolved = resolve_input({"a": "{{ input.x }}", "b": "{{ input.y }}"},
                             {"x": None, "y": ""}, None, {})
    assert resolved == {"a": None, "b": ""}


def test_nested_missing_input_segment_resolves_to_none():
    resolved = resolve_input({"v": "{{ input.meta.lang }}"}, {"meta": {}}, None, {})
    assert resolved == {"v": None}


def test_prev_and_step_refs_still_strict():
    """prev / step[n].output 是流内接线：缺了就报错，不静默变 None。"""
    with pytest.raises(ToolUserError, match="管线模板引用不存在"):
        resolve_input({"x": "{{ prev.missing }}"}, {}, {"other": 1}, {})
    with pytest.raises(ToolUserError, match="管线模板引用不存在"):
        resolve_input({"x": "{{ step[0].output.missing }}"}, {}, None, {0: {"other": 1}})


def test_input_keys_are_not_required_to_exist_at_all():
    """历史 run 的 input 只有 file：所有模板键缺失也能解析（重跑/降级可跑通）。"""
    resolved = resolve_input(
        {"file": "{{ input.file }}", "key_name": "{{ input.key_name }}",
         "target_lang": "{{ input.target_lang }}", "terms": "{{ input.terms }}",
         "mode": "{{ input.mode }}"}, {"file": "/tmp/x.docx"}, None, {})
    assert resolved == {"file": "/tmp/x.docx", "key_name": None, "target_lang": None,
                        "terms": None, "mode": None}
