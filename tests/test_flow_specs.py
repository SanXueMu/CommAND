"""流定义 × 工具清单 × 站点声明的一致性（静态防拼写回归）。

register_translee_flows.py 的 FLOWS 是纯数据：步骤引用的**工具 id**、**入参键名**一旦拼错，
要到线上真跑任务才暴露；翻译工作台声明里的 routes/params 指向不存在的流则表单直接失效。
本测试在测试层静态校验三者一致：

1) 每个步骤的工具已注册，入参键 ∈ 工具 input_schema.properties，且工具必填项齐备；
2) 每条流都有流级 input_schema（工作台表单依赖它渲染）；
3) 工作台声明的 routes[].flow / params[].when_flow 都指向 FLOWS 里真实存在的流。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.protocol import ToolManifest
from store.site_views.translate import TRANSLATE_VIEW

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "scripts" / "register_translee_flows.py"


@pytest.fixture(scope="module")
def register():
    spec = importlib.util.spec_from_file_location("register_translee_flows", REGISTER_PATH)
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


def test_flow_steps_reference_known_tools_and_params(register, manifests) -> None:
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


def test_every_flow_has_flow_level_input_schema(register) -> None:
    """工作台表单按流级 input_schema 渲染（中文 title/format:file），缺一家即表单空白。"""
    for flow_id in register.FLOWS:
        schema = register.INPUT_SCHEMAS.get(flow_id)
        assert schema, f"{flow_id} 缺流级 input_schema"
        assert schema["type"] == "object"
        assert "file" in schema["properties"], f"{flow_id} 表单须含 file 字段"


def test_translate_docx_flow_wiring(register) -> None:
    spec = register.FLOWS["flow.translate.docx"]
    assert [s["tool"] for s in spec["steps"]] == [
        "docx.extract.units", "table.classify.columns", "text.dedup.values",
        "text.llm.translate", "text.verify.fidelity", "docx.render.translated",
    ]
    render = spec["steps"][5]["input"]
    # 回填取**原始 docx**（非中间产物）与 step[0] 单元、step[1] 列分类、去重映射、质检状态
    assert render["file"] == "{{ input.file }}"
    assert render["units"] == "{{ step[0].output.units }}"
    assert render["col_classes"] == "{{ step[1].output.col_classes }}"
    assert render["index_map"] == "{{ step[2].output.index_map }}"
    assert render["statuses"] == "{{ step[4].output.statuses }}"
    assert render["mode"] == "{{ input.mode }}"
    # 默认双语对照（用户口径）；模板引用的可选参数必须在场（值可为 null）
    assert register.INPUT_SCHEMAS["flow.translate.docx"]["properties"]["mode"]["default"] == "bilingual"


def test_translate_view_declaration_consistent(register) -> None:
    props = TRANSLATE_VIEW["props"]
    known = set(register.FLOWS)
    for route in props["routes"]:
        assert route["flow"] in known, f"声明路由指向未注册的流: {route}"
        assert route["ext"] and all(e.startswith(".") for e in route["ext"])
    for param in props["params"]:
        for flow_id in param.get("when_flow", []):
            assert flow_id in known, f"参数 {param['name']} 的 when_flow 指向未注册的流: {flow_id}"


def test_translate_view_docx_route_and_mode_default(register) -> None:
    props = TRANSLATE_VIEW["props"]
    docx_routes = [r for r in props["routes"] if ".docx" in r["ext"]]
    assert [r["flow"] for r in docx_routes] == ["flow.translate.docx"]
    mode = next(p for p in props["params"] if p["name"] == "mode")
    assert "flow.translate.docx" in mode["when_flow"]
    assert mode["default"] == "overlay", "PDF 版式流默认原位覆盖"
    assert mode["default_by_flow"] == {"flow.translate.docx": "bilingual"}, "Word 流默认双语对照"
    values = {o["value"] for o in mode["options"]}
    assert values == {"overlay", "bilingual"}


def test_translate_view_unsupported_doc_hint() -> None:
    rules = TRANSLATE_VIEW["props"]["unsupported"]
    doc = next(r for r in rules if ".doc" in r["ext"])
    assert "另存为 .docx" in doc["message"]


def test_translate_view_batch_extensions_are_routable() -> None:
    """批量入口允许的扩展名必须都有路由，否则会「传上来却入不了队」。"""
    props = TRANSLATE_VIEW["props"]
    batch = props.get("batch")
    assert batch, "翻译声明缺 batch（前端批量入口不会显示）"
    routed = {e.lower() for r in props["routes"] for e in r["ext"]}
    assert [e for e in batch["extensions"] if e.lower() not in routed] == []
    unsupported = {e.lower() for r in props.get("unsupported", []) for e in r["ext"]}
    assert not (set(batch["extensions"]) & unsupported), "批量允许的后缀不能同时被声明为不支持"
    assert batch["maxFiles"] > 0 and batch["maxTotalMB"] > 0


def test_translate_view_default_by_flow_stays_visible() -> None:
    """default_by_flow 的流必须同时在 when_flow 内，否则该流下参数不可见、默认值形同虚设。"""
    for param in TRANSLATE_VIEW["props"]["params"]:
        visible = set(param.get("when_flow", []))
        for flow_id, value in (param.get("default_by_flow") or {}).items():
            assert flow_id in visible, f"{param['name']} 的 default_by_flow 流 {flow_id} 不在 when_flow 内"
            if param.get("type") == "select":
                assert value in {o["value"] for o in param.get("options", [])}
