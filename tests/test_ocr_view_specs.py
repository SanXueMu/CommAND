"""OCR 流定义 × 工具清单 × 站点声明的一致性（静态防拼写回归）。

与 test_flow_specs.py 同思路，覆盖 register_ocr_flows.py 的 FLOWS：
1) 每个步骤的工具已注册、入参键 ∈ 工具 input_schema.properties、工具必填项齐备；
2) 每条流都有流级 input_schema（工作台表单依赖它渲染）；
3) OCR 工作台声明的 recognizeFlow/exportFlow/searchableFlow 都指向 FLOWS 里真实存在的流；
4) 批量入口声明的后缀/上限合法（与翻译工作台同口径）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.protocol import ToolManifest
from store.site_views.ocr import OCR_VIEW

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "scripts" / "register_ocr_flows.py"


@pytest.fixture(scope="module")
def register():
    spec = importlib.util.spec_from_file_location("register_ocr_flows", REGISTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 仅定义常量与函数（argparse 在 __main__ 守卫内）
    return module


@pytest.fixture(scope="module")
def manifests() -> dict[str, ToolManifest]:
    out: dict[str, ToolManifest] = {}
    for path in sorted(ROOT.glob("tools/**/tool.toml")):
        manifest = ToolManifest.from_toml(path)
        out[manifest.tool.id] = manifest
    assert out, "未扫描到任何工具清单"
    return out


def test_ocr_flow_steps_reference_known_tools_and_params(register, manifests) -> None:
    for flow_id, spec in register.FLOWS.items():
        for index, step in enumerate(spec["steps"]):
            tool_id = step["tool"]
            assert tool_id in manifests, f"{flow_id} 第 {index} 步工具未注册: {tool_id}"
            schema = manifests[tool_id].io.input_schema
            properties = set(schema.get("properties") or {})
            provided = set(step["input"])
            unknown = provided - properties
            assert not unknown, f"{flow_id} 第 {index} 步 {tool_id} 入参键不在 schema: {sorted(unknown)}"
            missing = set(schema.get("required") or []) - provided
            assert not missing, f"{flow_id} 第 {index} 步 {tool_id} 缺少必填入参: {sorted(missing)}"


def test_every_ocr_flow_has_flow_level_input_schema(register) -> None:
    for flow_id in register.FLOWS:
        schema = register.INPUT_SCHEMAS.get(flow_id)
        assert schema, f"{flow_id} 缺流级 input_schema"
        assert schema["type"] == "object"
        assert schema.get("properties"), f"{flow_id} 流级 input_schema 无任何字段（表单会空白）"


def test_ocr_view_flows_are_registered(register) -> None:
    props = OCR_VIEW["props"]
    # genFlow（「新建模版」跳转）已随按钮一并删除：模板新建走模板弹窗内部
    for key in ("recognizeFlow", "exportFlow", "searchableFlow"):
        flow_id = props.get(key)
        assert flow_id, f"OCR 声明缺 {key}"
        assert flow_id in register.FLOWS, f"{key} 指向未注册的流: {flow_id}"
    assert props["viewTool"] in {m.tool.id for m in [ToolManifest.from_toml(p) for p in ROOT.glob("tools/**/tool.toml")]}


def test_ocr_view_batch_declaration_sane() -> None:
    batch = OCR_VIEW["props"].get("batch")
    assert batch, "OCR 声明缺 batch（前端批量入口不会显示）"
    assert all(e.startswith(".") for e in batch["extensions"]), batch["extensions"]
    assert {"pdf", "png", "jpg"} <= {e.lstrip(".") for e in batch["extensions"]}
    assert batch["maxFiles"] > 0 and batch["maxTotalMB"] > 0
