"""OCR 流接线守卫（V1）：把翻译流的两组守卫盖到 register_ocr_flows。

线上实例：flow.ocr.recognize 第 1 步 `"db": "{{ input.output_db }}"`，用户没填
「结果库名」→ None，而 vl_extract 的 db 声明为纯 string → 入队即失败
「input 不符合 schema（$.db）」。此守卫让该类键漂移在测试期即暴露。
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from core.protocol import ToolManifest

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "scripts" / "register_ocr_flows.py"


@pytest.fixture(scope="module")
def register():
    spec = importlib.util.spec_from_file_location("register_ocr_flows_test", REGISTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifests() -> dict[str, ToolManifest]:
    out: dict[str, ToolManifest] = {}
    for path in sorted(ROOT.glob("tools/**/tool.toml")):
        manifest = ToolManifest.from_toml(path)
        out[manifest.tool.id] = manifest
    return out


def test_ocr_flow_steps_reference_known_tools_and_params(register, manifests) -> None:
    for flow_id, spec in register.FLOWS.items():
        for index, step in enumerate(spec["steps"]):
            tool_id = step["tool"]
            assert tool_id in manifests, f"{flow_id} 第 {index} 步工具未注册: {tool_id}"
            schema = manifests[tool_id].io.input_schema
            properties = set(schema.get("properties") or {})
            unknown = set(step["input"]) - properties
            assert not unknown, f"{flow_id} 第 {index} 步 {tool_id} 入参键不在 schema: {sorted(unknown)}"
            missing = set(schema.get("required") or []) - set(step["input"])
            assert not missing, f"{flow_id} 第 {index} 步 {tool_id} 缺少必填入参: {sorted(missing)}"


def test_every_ocr_flow_has_input_schema(register) -> None:
    for flow_id in register.FLOWS:
        assert register.INPUT_SCHEMAS.get(flow_id), f"{flow_id} 缺流级 INPUT_SCHEMA（表单渲染依赖）"


def _allows_null(schema: dict) -> bool:
    t = schema.get("type")
    if isinstance(t, list):
        return "null" in t
    return "enum" in schema and None in schema["enum"]


def test_optional_ocr_flow_keys_map_to_nullable_tool_params(register, manifests) -> None:
    """可选流键被模板**整串引用**时，对应工具参数必须可空（同翻译流 P1 守卫）。"""
    for flow_id, spec in register.FLOWS.items():
        schema = register.INPUT_SCHEMAS.get(flow_id) or {}
        required = set(schema.get("required") or [])
        for index, step in enumerate(spec["steps"]):
            tool = manifests.get(step["tool"])
            if tool is None:
                continue
            props = tool.io.input_schema.get("properties") or {}
            for param, template in step["input"].items():
                if not isinstance(template, str):
                    continue
                match = re.fullmatch(r"\s*\{\{\s*input\.(\w+)\s*\}\}\s*", template)
                if not match or match.group(1) in required:
                    continue
                assert _allows_null(props.get(param) or {}), (
                    f"{flow_id} 第 {index} 步：可选流键 input.{match.group(1)} → 工具参数 "
                    f"{param} 必须可空（type 含 null），否则缺值时入队即失败")
