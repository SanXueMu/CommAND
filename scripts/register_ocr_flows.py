"""注册 CommOCR 移植管线（幂等）：扫描工具 → 注册 8 条 flow。

用法：uv run python scripts/register_ocr_flows.py [--api http://127.0.0.1:8000]
重复执行安全（同 id 覆盖注册）。模板三件套数据来自 scripts/ocr_builtin_templates.py
（CommOCR builtin_templates.py 原样拷贝）。

管线一览：
  flow.ocr.recognize   通用识别（参数全开放）
  flow.ocr.invoice     模板：识别发票凭证（提示词+钩子固化）
  flow.ocr.contract    模板：识别历史合同
  flow.ocr.audit       模板：识别决算审定表（lenient 宽松）
  flow.ocr.translate   识别→translee 全链批翻（跨域复用）
  flow.ocrdb.view      读库→视图查询→xlsx 导出
  flow.specgen.pdf     方案一：非LLM布局分析→纯语言LLM→三件套校验
  flow.specgen.img     方案二：多模态直读→三件套校验
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ocr_builtin_templates import (  # noqa: E402
    CONTRACT_FIELDS, CONTRACT_TEMPLATE, SHENBAO_FIELDS, SHENBAO_TEMPLATE,
    SHENBAO_RULES, SHENBAO_EXAMPLE, SHENBAO_POSTPROCESS_CODE,
    VOUCHER_FIELDS, VOUCHER_TEMPLATE, VOUCHER_RULES, VOUCHER_EXAMPLE,
    VOUCHER_POSTPROCESS_CODE,
)

API = "http://127.0.0.1:8000"


def _filled(template: str, fields: list[str], rules: list[str], example) -> str:
    """CommOCR 同款逐占位符替换（str.format 会被模板内 JSON 花括号炸掉）。"""
    prompt = template
    replacements = {
        "{field_count}": str(len(fields)),
        "{fields}": "、".join(fields),
        "{rules}": "\n".join(rules) if isinstance(rules, list) else (rules or ""),
        "{example}": json.dumps(example, ensure_ascii=False, indent=2) if example else "",
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def _tpl_flow(flow_id: str, name: str, fields: list[str], template: str,
              rules: list[str] | None, example, hooks: list[dict],
              record_mode: str, lenient: bool) -> dict:
    vl_input: dict = {
        "file": "{{ input.file }}",
        "db": "{{ input.output_db }}",
        "key_name": "{{ input.key_name }}",
        "model": "{{ input.model }}",
        "raw_prompt": True,
        "prompt": _filled(template, fields, rules or [], example),
        "fields": fields,
        "record_mode": record_mode,
        "skip_text_pdf": "{{ input.skip_text_pdf }}",
    }
    if lenient:
        vl_input["lenient"] = True
    if hooks:
        vl_input["postprocess"] = [{"name": h["name"], "code": h["code"]} for h in hooks]
    return {
        "name": name,
        "steps": [{"tool": "img.vl.extract", "input": vl_input}],
    }


FLOWS: dict[str, dict] = {
    "flow.ocr.recognize": {
        "name": "通用识别（参数全开放：fields/prompt/钩子自备）",
        "steps": [{
            "tool": "img.vl.extract",
            "input": {
                "file": "{{ input.file }}", "db": "{{ input.output_db }}",
                "key_name": "{{ input.key_name }}", "model": "{{ input.model }}",
                "fields": "{{ input.fields }}", "prompt": "{{ input.prompt }}",
                "rules": "{{ input.rules }}", "example": "{{ input.example }}",
                "record_mode": "{{ input.record_mode }}",
                "skip_text_pdf": "{{ input.skip_text_pdf }}",
                "postprocess": "{{ input.postprocess }}",
            },
        }],
    },
    "flow.ocr.invoice": _tpl_flow(
        "flow.ocr.invoice", "识别发票凭证（模板固化：金额归一+借贷校验+大写兜底钩子）",
        VOUCHER_FIELDS, VOUCHER_TEMPLATE, VOUCHER_RULES, VOUCHER_EXAMPLE,
        [{"name": "凭证金额校验与大写兜底", "code": VOUCHER_POSTPROCESS_CODE}],
        record_mode="page", lenient=False),
    "flow.ocr.contract": _tpl_flow(
        "flow.ocr.contract", "识别历史合同（模板固化：三线索字段）",
        CONTRACT_FIELDS, CONTRACT_TEMPLATE, None, None, [],
        record_mode="page", lenient=False),
    "flow.ocr.audit": _tpl_flow(
        "flow.ocr.audit", "识别决算审定表（模板固化：lenient 宽松+金额归一勾稽钩子）",
        SHENBAO_FIELDS, SHENBAO_TEMPLATE, SHENBAO_RULES, SHENBAO_EXAMPLE,
        [{"name": "审定表金额归一与勾稽校验", "code": SHENBAO_POSTPROCESS_CODE}],
        record_mode="page", lenient=True),
    "flow.ocr.translate": {
        "name": "识别→批翻全自动流（OCR→提取单元→分类→去重→翻译→双语回填，复用 translee 全链）",
        "steps": [
            {"tool": "img.vl.extract", "input": {
                "file": "{{ input.file }}", "db": "{{ input.output_db }}",
                "key_name": "{{ input.key_name }}",
                "fields": "{{ input.fields }}", "prompt": "{{ input.prompt }}",
                "record_mode": "{{ input.record_mode }}",
            }},
            {"tool": "ocrdb.extract.units", "input": {"file": "{{ prev.db }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.translate_key_name }}",
                "target_lang": "{{ input.target_lang }}",
            }},
            {"tool": "xlsx.backfill.dict", "input": {
                "units": "{{ step[1].output.units }}",
                "col_classes": "{{ step[2].output.col_classes }}",
                "ranges": "{{ step[2].output.ranges }}",
                "segments": "{{ step[2].output.segments }}",
                "index_map": "{{ step[3].output.index_map }}",
                "date_maps": "{{ step[3].output.date_maps }}",
                "translations": "{{ step[4].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}",
            }},
        ],
    },
    "flow.ocrdb.view": {
        "name": "视图导出流（读库→ViewSpec 查询→xlsx 多 sheet 导出）",
        "steps": [
            {"tool": "ocrdb.extract.units", "input": {
                "file": "{{ input.db }}", "mode": "records"}},
            {"tool": "records.view.query", "input": {
                "records": "{{ prev.records }}",
                "view_spec": "{{ input.view_spec }}"}},
            {"tool": "records.export.xlsx", "input": {
                "columns": "{{ prev.columns }}", "rows": "{{ prev.rows }}",
                "splits": "{{ prev.splits }}", "name": "{{ input.name }}"}},
        ],
    },
    "flow.specgen.pdf": {
        "name": "模板生成·方案一（非LLM布局分析→纯语言LLM→三件套校验；需文本层PDF）",
        "steps": [
            {"tool": "layout.analyze.pdf", "input": {"file": "{{ input.file }}"}},
            {"tool": "spec.gen.textllm", "input": {
                "requirement": "{{ input.requirement }}",
                "layout_json": "{{ prev.layout_json }}",
                "key_name": "{{ input.key_name }}", "model": "{{ input.model }}"}},
            {"tool": "spec.validate.ocrspec", "input": {
                "task_spec": "{{ prev.task_spec }}",
                "postprocess": "{{ prev.postprocess }}",
                "view_spec": "{{ prev.view_spec }}"}},
        ],
    },
    "flow.specgen.img": {
        "name": "模板生成·方案二（多模态直读样例→三件套校验；扫描件/图片通用）",
        "steps": [
            {"tool": "spec.gen.vl", "input": {
                "file": "{{ input.file }}", "requirement": "{{ input.requirement }}",
                "key_name": "{{ input.key_name }}", "model": "{{ input.model }}"}},
            {"tool": "spec.validate.ocrspec", "input": {
                "task_spec": "{{ prev.task_spec }}",
                "postprocess": "{{ prev.postprocess }}",
                "view_spec": "{{ prev.view_spec }}"}},
        ],
    },
}


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def main() -> None:
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    API = args.api.rstrip("/")

    tools = api("/api/tools/scan", method="POST")
    count = tools.get("registered") or len(tools.get("tools", tools)) 
    print(f"工具扫描响应: {json.dumps(tools, ensure_ascii=False)[:200]}")

    existing = {p["id"] for p in api("/api/pipelines").get("pipelines", [])}
    for flow_id, spec in FLOWS.items():
        body = {"id": flow_id, "name": spec["name"], "steps": spec["steps"]}
        api("/api/pipelines", method="POST", body=body)
        mark = "更新" if flow_id in existing else "新增"
        print(f"[{mark}] {flow_id}  ({len(spec['steps'])} 步)")
    print(f"完成：{len(FLOWS)} 条管线就绪")


if __name__ == "__main__":
    main()
