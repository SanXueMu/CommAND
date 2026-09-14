"""注册 Translee 翻译流（协议 v3：幂等 upsert + 流级 input_schema + legacy 清理）。

用法：uv run python scripts/register_translee_flows.py [--api http://127.0.0.1:8800]
重复执行安全（管线同 id 覆盖注册）。

三级概念布局：
  工具（tools/ 目录 scan 注册）——translee 十件 + 共享基建
  普通流（FLOWS）——flow.translate.xlsx / pdf / txt / docx / pdf.layout（线性六步，每步 SSE 可观测）
                   / image（单步图片翻译）
  工作流——暂无（翻译多样性在输入文件，无需模板/嵌套）

已废弃（v1 验证期产物，脚本自动 DELETE）：dev.double.reverse / text.double_reverse /
text.broken。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8800"

# 06 C3：流级 input_schema——流表单声明驱动（中文 title/description，CommWEB
# resolveForm 直读；format: file 自动挂上传组件）。
INPUT_SCHEMAS: dict[str, dict] = {
    "flow.translate.xlsx": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "表格文件", "description": "xlsx 工作簿，可译内容将被提取并翻译"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
            "source_lang": {"type": "string", "title": "源语言", "description": "如：英文 / 中文；留空自动判定"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（优先级最高，命中即固定译法）"},
        },
    },
    "flow.translate.pdf.image": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "扫描件 PDF",
                     "description": "无文字层的图片版 PDF：逐页图片翻译后合成译文 PDF（产出无文字层）"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "DashScope 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "image_model": {"type": "string", "title": "图片翻译模型",
                            "description": "留空用 qwen-mt-image-2.0（0.004 元/张，RPM 60，并发 2）"},
            "source_lang": {"type": "string", "title": "源语言",
                            "description": "留空自动识别；源或目标至少一方须为中文/英文"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（作为 terminologies 做术语干预）"},
            "image_domain_hint": {"type": "string", "title": "业务领域",
                                  "description": "如 审计财务；留空则用模版声明的领域"},
        },
    },
    "flow.translate.skip": {
        "type": "object",
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文件", "description": "本轮不处理的文件（如 PPT）"},
            "reason": {"type": "string", "title": "暂停原因",
                       "description": "展示给用户：为何跳过、如何继续（如「PPT 暂不支持翻译」）"},
        },
    },
    "flow.translate.image": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "图片文件", "description": "png/jpg/jpeg/webp/tif/tiff/bmp"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "DashScope 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "image_model": {"type": "string", "title": "图片翻译模型", "description": "留空用 qwen-mt-image-2.0（0.004 元/张，约 1 分钟/张）"},
            "source_lang": {"type": "string", "title": "源语言", "description": "留空自动识别；源或目标至少一方须为中文/英文"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（作为 terminologies 做术语干预）"},
            "image_domain_hint": {"type": "string", "title": "业务领域",
                                  "description": "如 审计财务 / legal；留空则用模版声明的领域"},
            "image_segment": {"type": "boolean", "title": "仅翻译主体", "description": "商品图等只翻主体区域"},
        },
    },
    "flow.translate.pdf": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文档文件", "description": "pdf 文档，按页提取整段翻译，产出双语 docx"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
            "source_lang": {"type": "string", "title": "源语言", "description": "如：英文 / 中文；留空自动判定"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（优先级最高，命中即固定译法）"},
        },
    },
    "flow.translate.txt": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文本文件", "description": "txt/md 纯文本，逐段翻译，产出双语 docx"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
            "source_lang": {"type": "string", "title": "源语言", "description": "如：英文 / 中文；留空自动判定"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（优先级最高，命中即固定译法）"},
        },
    },
    "flow.translate.docx": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "Word 文档",
                     "description": "docx 文档，正文段落与表格整段翻译（旧版 .doc 请先另存为 .docx）"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
            "source_lang": {"type": "string", "title": "源语言", "description": "如：英文 / 中文；留空自动判定"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（优先级最高，命中即固定译法）"},
            "mode": {"type": "string", "title": "输出模式", "enum": ["bilingual", "overlay"],
                     "default": "bilingual",
                     "description": "bilingual=原文段落 + 译文段落（双语对照）；overlay=原位覆盖单语译文（保留原版式）"},
        },
    },
    "flow.translate.pdf.layout": {
        "type": "object",
        "required": ["file", "key_name", "target_lang"],
        "properties": {
            "file": {"type": "string", "format": "file", "title": "文档文件",
                     "description": "pdf 文档（含扫描/图片版，自动 OCR 补层），按版式块翻译"},
            "key_name": {"type": "string", "title": "密钥名称", "description": "设置页已录入的 LLM 密钥名"},
            "target_lang": {"type": "string", "title": "目标语言", "description": "如：中文 / English"},
            "model": {"type": "string", "title": "翻译模型", "description": "留空用密钥默认模型"},
            "source_lang": {"type": "string", "title": "源语言", "description": "如：英文 / 中文；留空自动判定"},
            "terms": {"type": "string", "format": "textarea", "title": "术语表",
                      "description": "每行：原文 => 译文（优先级最高，命中即固定译法）"},
            "mode": {"type": "string", "title": "输出模式", "enum": ["overlay", "bilingual"],
                     "default": "overlay",
                     "description": "overlay=原位覆盖单语译文；bilingual=左右分栏双语对照"},
        },
    },
}

FLOWS: dict[str, dict] = {
    "flow.translate.xlsx": {
        "name": "表格翻译", "doc_md": "xlsx 翻译全自动流：提取→分类→归一去重→翻译→质检→回填。产物为「原文｜译文」并排的中文版 xlsx（每个原 sheet 之后插入 <sheet名>_翻译结果，原 sheet 原样保留）。",
        "steps": [
            {"tool": "xlsx.extract.values", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "xlsx.backfill.dict", "input": {
                "units": "{{ step[0].output.units }}",
                "col_classes": "{{ step[1].output.col_classes }}",
                "ranges": "{{ step[1].output.ranges }}",
                "segments": "{{ step[1].output.segments }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
    "flow.translate.pdf": {
        "name": "文档翻译", "doc_md": "pdf 翻译全自动流：按页提取→分类→归一去重→长文翻译→质检→双语 docx 渲染。",
        "steps": [
            {"tool": "pdf.extract.pages", "input": {"file": "{{ input.file }}", "auto_ocr": True}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
    "flow.translate.txt": {
        "name": "文本翻译", "doc_md": "txt/md 翻译全自动流：提取→分类→归一去重→翻译→质检→双语 docx 渲染。",
        "steps": [
            {"tool": "txt.extract.text", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "docx.render.bilingual", "input": {
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "file": "{{ input.file }}"}},
        ],
    },
    "flow.translate.docx": {
        "name": "Word 翻译",
        "doc_md": ("docx 翻译全自动流：正文流提取（段落/表格保序，跳过空段/数字/域代码）→分类→归一去重"
                   "→翻译→质检→译文回填（段落对照双语 / 原位覆盖单语，保留样式与图片）。"),
        "steps": [
            {"tool": "docx.extract.units", "input": {"file": "{{ input.file }}"}},
            {"tool": "table.classify.columns", "input": {"units": "{{ prev.units }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "docx.render.translated", "input": {
                "file": "{{ input.file }}",
                "units": "{{ step[0].output.units }}",
                "ranges": "{{ step[1].output.ranges }}",
                "col_classes": "{{ step[1].output.col_classes }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "mode": "{{ input.mode }}"}},
        ],
    },
    "flow.translate.pdf.image": {
        "name": "图片版 PDF 翻译",
        # 失败降级（015/016）：qwen-mt-image 未开通/无权限/不存在时，自动改用版式翻译流
        # （pdf.extract.blocks 自带 ocrmypdf 补文字层 → 文本翻译 → 双语/原位 PDF），即「原方案」
        "on_failure": {"fallback_flow": "flow.translate.pdf.layout"},
        "doc_md": ("图片版 PDF 翻译全自动流（扫描件专用）：每页转图片 → 逐页图片翻译（qwen-mt-image，"
                   "并发 2 + RPM 60 限速，术语/业务域可干预）→ 译文页图按页序合成译文 PDF（保留原版式）。"
                   "产出为图片版 PDF（无文字层，不可选中搜索）；如需可搜索文字版，请先用 ocrmypdf 补文字层再走版式流。"),
        "steps": [
            {"tool": "pdf.pages.to_images", "input": {"file": "{{ input.file }}"}},
            {"tool": "image.batch.translate", "input": {
                "images": "{{ prev.paths }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "domain_hint": "{{ input.image_domain_hint }}",
                "model": "{{ input.image_model }}"}},
            {"tool": "pdf.from.images", "input": {
                "images": "{{ prev.paths }}",
                "source_file": "{{ input.file }}",
                "cleanup_dirs": ["{{ step[0].output.dir }}", "{{ step[1].output.output_dir }}"]}},
        ],
    },
    "flow.translate.skip": {
        "name": "暂不翻译（暂停留档）",
        "doc_md": ("刻意不处理本文件（如 PPT / 指定文字版但为扫描件）：1 步流并**暂停**留档，"
                   "让用户看到「哪些文件没处理、为什么」；源文件仍随批次导出（目录结构与原结构一致）。"),
        "steps": [
            {"tool": "file.skip.pause", "input": {
                "file": "{{ input.file }}",
                "reason": "{{ input.reason }}"}},
        ],
    },
    "flow.translate.image": {
        "name": "图片翻译",
        # 单图没有文字等价方案：模型不可用（403/未开通）时降级到 skip 流 → **暂停留档**
        # （可见、可决策；源文件随批次导出），而不是留一条红色失败
        "on_failure": {"fallback_flow": "flow.translate.skip"},
        "doc_md": ("图片翻译全自动流：本地图片 → DashScope 临时上传 → 异步图片翻译（qwen-mt-image-2.0）"
                   "→ 下载译文图（保留排版）。术语干预对接术语表；主模型不可用自动降级备用模型。"
                   "限速：RPM 60（约 1 秒/张）。"),
        "steps": [
            {"tool": "image.mt.translate", "input": {
                "file": "{{ input.file }}",
                "model": "{{ input.image_model }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "domain_hint": "{{ input.image_domain_hint }}"}},
        ],
    },
    "flow.translate.pdf.layout": {
        "name": "版式翻译", "doc_md": "pdf 版式翻译全自动流：扫描页自动 OCR 补层→版式块提取→归一去重→翻译→质检→版式渲染（原位覆盖 / 左右分栏双语）。",
        "steps": [
            {"tool": "pdf.extract.blocks", "input": {"file": "{{ input.file }}", "auto_ocr": True}},
            {"tool": "pdf.blocks.to_segments", "input": {"blocks": "{{ prev.blocks }}"}},
            {"tool": "text.dedup.values", "input": {"segments": "{{ prev.segments }}"}},
            {"tool": "text.llm.translate", "input": {
                "segments": "{{ prev.unique }}",
                "key_name": "{{ input.key_name }}",
                "target_lang": "{{ input.target_lang }}",
                "source_lang": "{{ input.source_lang }}",
                "terms": "{{ input.terms }}",
                "model": "{{ input.model }}"}},
            {"tool": "text.verify.fidelity", "input": {
                "sources": "{{ step[2].output.unique }}",
                "translations": "{{ prev.translations }}"}},
            {"tool": "pdf.render.translated", "input": {
                "file": "{{ step[0].output.render_file }}",
                "blocks": "{{ step[0].output.blocks }}",
                "index_map": "{{ step[2].output.index_map }}",
                "date_maps": "{{ step[2].output.date_maps }}",
                "translations": "{{ step[3].output.translations }}",
                "statuses": "{{ step[4].output.statuses }}",
                "mode": "{{ input.mode }}"}},
        ],
    },
}

LEGACY_FLOWS = ["dev.double.reverse", "text.double_reverse", "text.broken"]


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
    parser.add_argument("--api", default="http://127.0.0.1:8800")
    parser.add_argument("--keep-legacy", action="store_true",
                        help="保留 v1 验证期遗留流（默认删除）")
    args = parser.parse_args()
    API = args.api.rstrip("/")

    tools = api("/api/tools/scan", method="POST")
    print(f"工具扫描响应: {json.dumps(tools, ensure_ascii=False)[:200]}")

    for legacy in LEGACY_FLOWS:
        if args.keep_legacy:
            continue
        try:
            api(f"/api/pipelines/{legacy}", method="DELETE")
            print(f"[删除] {legacy}（v1 验证期遗留）")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[跳过] {legacy}（不存在）")
            else:
                raise

    for pid, spec in FLOWS.items():
        body = {"id": pid, "name": spec["name"], "steps": spec["steps"],
                "doc_md": spec.get("doc_md"),
                "input_schema": INPUT_SCHEMAS.get(pid),
                "on_failure": spec.get("on_failure")}
        api("/api/pipelines", method="POST", body=body)
        print(f"[注册] {pid}（{spec['name']}，input_schema ✓）")

    pipelines = api("/api/pipelines").get("pipelines", [])
    print(f"当前管线 {len(pipelines)} 条: {[p['id'] for p in pipelines]}")


if __name__ == "__main__":
    main()
