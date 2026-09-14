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
import re
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


def test_translate_bilingual_flows_wire_col_classes(register) -> None:
    """docx.render.bilingual 必须拿到 col_classes —— 漏接线时表格只翻表头、数据格回落原文。"""
    for flow_id in ("flow.translate.pdf", "flow.translate.txt"):
        steps = register.FLOWS[flow_id]["steps"]
        assert steps[-1]["tool"] == "docx.render.bilingual", flow_id
        render = steps[-1]["input"]
        assert render["units"] == "{{ step[0].output.units }}"
        assert render["ranges"] == "{{ step[1].output.ranges }}"
        assert render["col_classes"] == "{{ step[1].output.col_classes }}", (
            f"{flow_id} 的 docx.render.bilingual 未接线 col_classes（表格单元格拿不到译文）")


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
    assert "flow.translate.pdf.layout" in mode["when_flow"]
    # 2026-09-14 用户口径：版式与 Word 均默认双语对照（原位覆盖仍可手动选）
    assert mode["default"] == "bilingual", "默认双语对照"
    assert mode["default_by_flow"] == {"flow.translate.docx": "bilingual"}, "Word 流默认双语对照"
    values = {o["value"] for o in mode["options"]}
    assert values == {"overlay", "bilingual"}
    # 流级 schema 的默认值须与工作台声明一致（FlowRunner 表单同源）
    assert register.INPUT_SCHEMAS["flow.translate.pdf.layout"]["properties"]["mode"]["default"] == "bilingual"


def test_translate_view_legacy_doc_pauses_instead_of_rejecting() -> None:
    """旧版 .doc 改成可提交：路由到 Word 流，由工具抛 ToolPauseError 暂停子任务等人工另存为 .docx。"""
    props = TRANSLATE_VIEW["props"]
    doc = next(r for r in props["routes"] if ".doc" in [e.lower() for e in r["ext"]])
    assert doc["flow"] == "flow.translate.docx"
    assert "暂停" in doc["label"]
    assert ".doc" not in {e.lower() for r in props.get("unsupported", []) for e in r["ext"]}


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


# ── 流模板入参键守卫（2026-09-14 线上事故根因）──────────────────────────────
# 事故：PNG 全挂（模板要 input.domain_hint，声明发的是 image_domain_hint）、
# PDF 全挂（前端按「扩展名默认流」取参数，实际跑的是探测后的图片流，漏发 image_model）。
# 两处漂移的共性 = 「模板引用的键」与「前端能发出的键」不一致 → 引擎严格解析直接入队失败。
# 下面两条守卫把这类漂移钉死在提交前。

# 前端固定发送、不由声明参数渲染的核心键
_CORE_INPUT_KEYS = {"file", "key_name", "source_lang", "target_lang", "terms", "reason"}
_INPUT_REF_RE = re.compile(r"\{\{\s*input\.([A-Za-z_]\w*)")


def _template_input_keys(value, acc: set[str]) -> set[str]:
    """递归收集模板里引用的 input 键（{{ input.X }}，含嵌套 dict/list）。"""
    if isinstance(value, str):
        acc |= set(_INPUT_REF_RE.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            _template_input_keys(item, acc)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _template_input_keys(item, acc)
    return acc


def _visible_param_names(flow_id: str) -> set[str]:
    names: set[str] = set()
    for param in TRANSLATE_VIEW["props"]["params"]:
        if flow_id in param.get("when_flow", []):
            names.add(param["name"])
    return names


def test_flow_templates_reference_keys_declared_in_flow_schema(register) -> None:
    """① 模板引用的每个 input 键都必须在该流 INPUT_SCHEMAS.properties 里声明。"""
    for flow_id, spec in register.FLOWS.items():
        schema_props = set((register.INPUT_SCHEMAS.get(flow_id) or {}).get("properties") or {})
        for index, step in enumerate(spec["steps"]):
            for key in sorted(_template_input_keys(step["input"], set())):
                assert key in schema_props, (
                    f"{flow_id} 第 {index} 步模板引用 {{{{ input.{key} }}}}，"
                    f"但该流 input_schema 未声明（前端表单不会有这个字段）")


def test_flow_templates_reference_keys_frontend_can_send(register) -> None:
    """② 模板引用的键必须是「前端在该流下能发出」的：声明参数（when_flow 命中）或核心键。

    否则前端根本不发这个键 → 引擎严格解析 → 入队失败（线上事故类型）。
    """
    for flow_id, spec in register.FLOWS.items():
        allowed = _visible_param_names(flow_id) | _CORE_INPUT_KEYS
        for index, step in enumerate(spec["steps"]):
            unreachable = sorted(_template_input_keys(step["input"], set()) - allowed)
            assert not unreachable, (
                f"{flow_id} 第 {index} 步模板引用了工作台声明里对该流不可见的键 {unreachable}"
                f"（前端不会发送 → 入队必失败）；请把该键加入 store/site_views/translate.py 的 params"
                f"（when_flow 含该流），或从模板里去掉")



def test_on_failure_fallback_flow_is_registered(register) -> None:
    """失败降级声明（015）的 fallback_flow 必须是本仓库已注册的流，且不能指向自身。"""
    for flow_id, spec in register.FLOWS.items():
        fallback = (spec.get("on_failure") or {}).get("fallback_flow")
        if not fallback:
            continue
        assert fallback in register.FLOWS, f"{flow_id} 的 fallback_flow 未注册: {fallback}"
        assert fallback != flow_id, f"{flow_id} 不能把自己声明为降级流（会无限降级）"


def test_image_pdf_flow_falls_back_to_layout_flow(register) -> None:
    """图片版 PDF 流（依赖 qwen-mt-image）必须声明降级到版式流——即用户口径的「原方案」。"""
    spec = register.FLOWS["flow.translate.pdf.image"]
    assert spec["on_failure"] == {"fallback_flow": "flow.translate.pdf.layout"}
    # 版式流自身不得再声明降级（避免链式降级）
    assert not register.FLOWS["flow.translate.pdf.layout"].get("on_failure")


def _allows_null(schema: dict) -> bool:
    t = schema.get("type")
    if isinstance(t, list):
        return "null" in t
    return "enum" in schema and None in schema["enum"]


def test_optional_flow_keys_map_to_nullable_tool_params(register, manifests) -> None:
    """可选流键被模板**整串引用**时，对应工具参数必须可空。

    否则该键缺值（重跑历史任务、降级继承 input、前端没发）会解析成 None →
    工具 input_schema 校验失败「None is not of type 'string'」→ 入队即失败。
    线上实例：flow.translate.skip 的 reason —— 图片流降级到 skip 后**降级 run 必失败**。
    """
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
                    continue  # 整串引用才解析为 None；必填键由调用方保证
                assert _allows_null(props.get(param) or {}), (
                    f"{flow_id} 第 {index} 步：可选流键 input.{match.group(1)} → 工具参数 "
                    f"{param} 必须可空（type 含 null），否则缺值时入队即失败")
