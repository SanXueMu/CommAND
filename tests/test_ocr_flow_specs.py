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


@pytest.fixture(scope="module")
def seed_templates(register):
    """种子模版（scripts/seed_ocr_templates.py 的 BUILTIN + CommOCR 迁移位图）。"""
    seed_path = ROOT / "scripts" / "seed_ocr_templates.py"
    spec = importlib.util.spec_from_file_location("seed_ocr_templates_test", seed_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._raw_templates()


def test_seed_template_input_schema_subset_of_smart_flow(register, seed_templates) -> None:
    """守卫第三层（X7）：模版 input_schema ⊆ flow.ocr.smart 的 INPUT_SCHEMA。

    模版声明的是 smart 流 schema 的**增量参数**——若模版出现流没有的键，
    或类型不兼容（流不接受 null 而模版允许），级联表单提交即入队失败
    （同族问题：H1 键名漂移 / V1 的 $.db）。模板与流的声明必须同源同步。
    """
    flow_schema = register.INPUT_SCHEMAS["flow.ocr.smart"]
    flow_props = flow_schema["properties"]
    flow_required = set(flow_schema.get("required", []))
    for tpl in seed_templates:
        schema = tpl.get("input_schema")
        if not schema:
            continue
        for key, decl in schema.get("properties", {}).items():
            assert key in flow_props, (
                f"{tpl.get('id')}: 模版参数 {key} 不在 flow.ocr.smart 的 INPUT_SCHEMA 里——"
                "级联表单会提交流不认识的键，或流模板引用取不到值")
            t_types = decl.get("type")
            f_types = flow_props[key].get("type")
            t_set = set([t_types] if isinstance(t_types, str) else t_types)
            f_set = set([f_types] if isinstance(f_types, str) else f_types)
            if key not in flow_required:
                # 可选键：流侧必须容忍缺失（null 或缺省），模版侧类型须落在流类型集内
                assert "null" in f_set, (
                    f"{tpl.get('id')}: 可选键 {key} 在流 schema 里不可空——留空提交会入队失败")
            assert t_set - {"null"} <= f_set - {"null"}, (
                f"{tpl.get('id')}: 模版参数 {key} 类型 {t_set} 超出流声明 {f_set}")


def test_voucher_rules_forbid_single_row_output() -> None:
    """AA1：多行硬规则必须渲染进最终 prompt（上游快照「只吐第一行」行为的加固）。"""
    import json

    from command_shared.ocr_engine import build_prompt

    spec = importlib.util.spec_from_file_location(
        "ocr_builtin_templates_prompt_test", ROOT / "scripts" / "ocr_builtin_templates.py")
    btm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(btm)

    rules = "\n".join(btm.VOUCHER_RULES)
    example = json.dumps(btm.VOUCHER_EXAMPLE, ensure_ascii=False, indent=2)
    rendered = build_prompt(btm.VOUCHER_TEMPLATE, btm.VOUCHER_FIELDS, rules, example, "page")
    assert "多行输出" in rendered and "严禁只输出第一行" in rendered
    assert example[:60] in rendered
