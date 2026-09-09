"""pipeline 模板解析纯函数测试：三变量 / 传值 / 插值 / 引用缺失。"""

import pytest

from core.errors import ToolUserError
from core.pipeline import resolve_input


def test_full_ref_passes_value_without_stringification():
    step = {"segments": "{{ input.segments }}"}
    resolved = resolve_input(step, {"segments": ["a", "b"]}, None, {})
    assert resolved == {"segments": ["a", "b"]}


def test_prev_whole_output_reference():
    resolved = resolve_input({"payload": "{{ prev }}"}, {}, {"x": 1}, {})
    assert resolved == {"payload": {"x": 1}}


def test_prev_field_reference():
    resolved = resolve_input({"segments": "{{ prev.translations }}"}, {},
                             {"translations": ["你", "好"]}, {})
    assert resolved == {"segments": ["你", "好"]}


def test_step_index_reference():
    history = {0: {"segments": ["one"]}, 1: {"segments": ["two"]}}
    resolved = resolve_input({"first": "{{ step[0].output.segments }}"},
                             {}, None, history)
    assert resolved == {"first": ["one"]}


def test_embedded_interpolation_becomes_string():
    resolved = resolve_input(
        {"title": "共 {{ input.count }} 段，来源 {{ input.source }}"},
        {"count": 3, "source": "word"}, None, {})
    assert resolved == {"title": "共 3 段，来源 word"}


def test_non_string_values_pass_through():
    resolved = resolve_input({"limit": 10, "flag": True, "opts": {"k": "v"}},
                             {}, None, {})
    assert resolved == {"limit": 10, "flag": True, "opts": {"k": "v"}}


def test_nested_containers_resolve_recursively():
    step = {"wrap": {"inner": ["{{ input.x }}", "静态"]}}
    resolved = resolve_input(step, {"x": [1, 2]}, None, {})
    assert resolved == {"wrap": {"inner": [[1, 2], "静态"]}}


def test_missing_reference_is_user_error():
    with pytest.raises(ToolUserError):
        resolve_input({"a": "{{ input.not_there }}"}, {}, None, {})
    with pytest.raises(ToolUserError):
        resolve_input({"a": "{{ prev.gone }}"}, {"gone": 1}, {}, {})
