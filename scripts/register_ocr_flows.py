"""注册 CommOCR 移植管线（幂等，06 E3 三级概念重写版）。

用法：uv run python scripts/register_ocr_flows.py [--api http://127.0.0.1:8000]
前置：uv run python scripts/seed_ocr_templates.py（三内置模版入库）

三级概念布局：
  工具（tools/ 目录 scan 注册）——含 E1 模版管理四件套 + resolve + from_spec
  普通流（FLOWS）——flow.ocr.recognize（通用全开放）/ flow.ocr.smart（模版驱动+
              when 条件导出）/ flow.ocr.translate / flow.ocrdb.view / flow.specgen.*
  工作流（WORKFLOWS）——wf.ocr.fullchain 真嵌套示范（specgen 子流→三件套转模版→
              smart 子流识别）

已废弃（模版化取代，脚本自动 DELETE）：flow.ocr.invoice / contract / audit
（近重复单步流→flow.ocr.smart + tpl.invoice.voucher / tpl.contract.history /
tpl.audit.shenbao 三模版）。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

API = "http://127.0.0.1:8000"

# 06 步8/C3：流级 input_schema——流表单声明驱动（中文 title/description，CommWEB
# resolveForm 直读；缺省时前端回退模板猜键，显示英文键名）。
INPUT_SCHEMAS: dict[str, dict] = {
    "flow.ocr.recognize": {
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string", "title": "识别文件", "description": "图片或 PDF 文件路径"},
            "output_db": {"type": "string", "title": "结果库名", "description": "识别结果写入的 OCR 库标识"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "model": {"type": "string", "title": "多模态模型", "description": "留空用默认模型"},
            "fields": {"type": "string", "title": "识别字段", "description": "JSON：字段名→说明"},
            "prompt": {"type": "string", "title": "识别提示词"},
            "rules": {"type": "string", "title": "识别规则"},
            "example": {"type": "string", "title": "输出示例"},
            "record_mode": {"type": "string", "title": "记录模式"},
            "skip_text_pdf": {"type": "boolean", "title": "文本层PDF直读", "description": "开启后带文本层的 PDF 不走视觉识别"},
            "postprocess": {"type": "string", "title": "后处理钩子", "description": "JSON 数组：字段名→规则表达式"},
        },
    },
    "flow.ocr.smart": {
        "type": "object",
        "required": ["template_id", "file"],
        "properties": {
            "template_id": {"type": "string", "title": "识别模版", "description": "选择模版后自动驱动识别（提示词/字段/钩子随模版）"},
            "file": {"type": "string", "title": "识别文件", "description": "图片或 PDF 文件路径"},
            "output_db": {"type": "string", "title": "结果库名", "description": "识别结果写入的 OCR 库标识"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "model": {"type": "string", "title": "多模态模型", "description": "留空用默认模型"},
            "skip_text_pdf": {"type": "boolean", "title": "文本层PDF直读", "description": "开启后带文本层的 PDF 不走视觉识别"},
            "export_units": {"type": "boolean", "title": "导出识别单元", "description": "识别完成后导出可翻译单元（供翻译流使用）"},
        },
    },
    "flow.ocr.translate": {
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string", "title": "识别文件", "description": "图片或 PDF 文件路径（识别+翻译+回填一步到位）"},
            "output_db": {"type": "string", "title": "结果库名", "description": "识别结果写入的 OCR 库标识"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "fields": {"type": "string", "title": "识别字段", "description": "JSON：字段名→说明"},
            "prompt": {"type": "string", "title": "识别提示词"},
            "record_mode": {"type": "string", "title": "记录模式"},
            "translate_key_name": {"type": "string", "title": "译文写入键名"},
            "target_lang": {"type": "string", "title": "目标语言"},
        },
    },
    "flow.ocrdb.view": {
        "type": "object",
        "required": ["db", "view_spec"],
        "properties": {
            "db": {"type": "string", "title": "OCR 库名", "description": "要导出的 OCR 结果库标识"},
            "view_spec": {"type": "string", "title": "视图定义", "description": "JSON：列/拆分 sheet 规则"},
            "name": {"type": "string", "title": "导出文件名"},
        },
    },
    "flow.specgen.pdf": {
        "type": "object",
        "required": ["file", "requirement"],
        "properties": {
            "file": {"type": "string", "title": "样例文件", "description": "带文本层的 PDF 样例"},
            "requirement": {"type": "string", "title": "识别需求描述", "description": "想从样例里得到什么字段、怎么用"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "model": {"type": "string", "title": "语言模型", "description": "留空用默认模型"},
        },
    },
    "flow.specgen.img": {
        "type": "object",
        "required": ["file", "requirement"],
        "properties": {
            "file": {"type": "string", "title": "样例文件", "description": "扫描件或图片样例"},
            "requirement": {"type": "string", "title": "识别需求描述", "description": "想从样例里得到什么字段、怎么用"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "model": {"type": "string", "title": "多模态模型", "description": "留空用默认模型"},
        },
    },
    "wf.ocr.fullchain": {
        "type": "object",
        "required": ["file", "requirement", "new_template_id"],
        "properties": {
            "file": {"type": "string", "title": "样例文件", "description": "同一份样例既生成模版又试识别"},
            "requirement": {"type": "string", "title": "识别需求描述"},
            "key_name": {"type": "string", "title": "记录主键名"},
            "model": {"type": "string", "title": "多模态模型"},
            "new_template_id": {"type": "string", "title": "新模版 ID", "description": "生成的模版以此 ID 入库"},
            "new_template_name": {"type": "string", "title": "新模版名称"},
            "output_db": {"type": "string", "title": "结果库名", "description": "试识别结果的入库标识"},
        },
    },
}

LEGACY_FLOWS = ("flow.ocr.invoice", "flow.ocr.contract", "flow.ocr.audit")

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
    # E2：模版驱动识别（resolve 渲染 → vl.extract 直驱 → when 条件导出）
    "flow.ocr.smart": {
        "name": "识别图片（模版驱动：按模板 id 渲染提示词与钩子；export_units 可选导出）",
        "steps": [
            {"tool": "spec.template.resolve",
             "input": {"id": "{{ input.template_id }}"}},
            {"tool": "img.vl.extract", "input": {
                "file": "{{ input.file }}", "db": "{{ input.output_db }}",
                "key_name": "{{ input.key_name }}", "model": "{{ input.model }}",
                "raw_prompt": True,
                "prompt": "{{ step[0].output.prompt }}",
                "fields": "{{ step[0].output.fields }}",
                "postprocess": "{{ step[0].output.hooks }}",
                "record_mode": "{{ step[0].output.record_mode }}",
                "lenient": "{{ step[0].output.lenient }}",
                "skip_text_pdf": "{{ input.skip_text_pdf }}"}},
            {"when": {"input.export_units": True},
             "tool": "ocrdb.extract.units",
             "input": {"file": "{{ input.output_db }}"}},
        ],
    },
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

# E3：真嵌套工作流示范——模板生成（子流）→ 三件套转模版 → 模版驱动识别（子流）
WORKFLOWS: dict[str, dict] = {
    "wf.ocr.fullchain": {
        "name": "全链工作流（模板生成→校验→入库为模版→模版驱动识别）",
        "steps": [
            {"pipeline": "flow.specgen.img", "input": {
                "file": "{{ input.file }}",
                "requirement": "{{ input.requirement }}",
                "key_name": "{{ input.key_name }}",
                "model": "{{ input.model }}"}},
            {"tool": "spec.template.from_spec", "input": {
                "id": "{{ input.new_template_id }}",
                "name": "{{ input.new_template_name }}",
                "category": "custom",
                "task_spec": "{{ step[0].output.task_spec }}",
                "postprocess": "{{ step[0].output.postprocess }}",
                "view_spec": "{{ step[0].output.view_spec }}"}},
            {"pipeline": "flow.ocr.smart", "input": {
                "template_id": "{{ step[1].output.id }}",
                "file": "{{ input.file }}",
                "output_db": "{{ input.output_db }}",
                "key_name": "{{ input.key_name }}",
                "model": "{{ input.model }}"}},
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
    parser.add_argument("--keep-legacy", action="store_true",
                        help="保留三条已废弃固化流（默认删除）")
    args = parser.parse_args()
    API = args.api.rstrip("/")

    tools = api("/api/tools/scan", method="POST")
    print(f"工具扫描响应: {json.dumps(tools, ensure_ascii=False)[:200]}")

    for legacy in LEGACY_FLOWS:
        if args.keep_legacy:
            continue
        try:
            api(f"/api/pipelines/{legacy}", method="DELETE")
            print(f"[删除] {legacy}（模版化取代 → flow.ocr.smart）")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[跳过] {legacy}（不存在）")
            else:
                raise

    existing = {p["id"] for p in api("/api/pipelines").get("pipelines", [])}
    for group_id, group in (("flow", FLOWS), ("workflow", WORKFLOWS)):
        for pid, spec in group.items():
            body = {"id": pid, "name": spec["name"], "steps": spec["steps"]}
            schema = INPUT_SCHEMAS.get(pid)
            if schema:
                body["input_schema"] = schema  # 06 C3：流表单中文声明（缺省则前端猜键）
            api("/api/pipelines", method="POST", body=body)
            mark = "更新" if pid in existing else "新增"
            print(f"[{mark}] {pid}  ({len(spec['steps'])} 步)")
    print(f"完成：{len(FLOWS)} 条普通流 + {len(WORKFLOWS)} 条工作流就绪")


if __name__ == "__main__":
    main()
