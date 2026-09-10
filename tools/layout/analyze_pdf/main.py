"""PDF 布局分析（非 LLM）：fitz 文本块/表格线框/表头候选/字段标签 → 布局描述 JSON。

模板生成方案一的前半程：为纯语言 LLM 提供「眼睛」——页数、每页表格结构
（线框行列 + 表头行 + 样例行）、大字/加粗表头候选、冒号结尾的字段标签。
纯 fitz 启发式，零模型成本；对扫描件（无文字层）能力有限，届时走方案二。
"""
from __future__ import annotations

import json
from pathlib import Path

from command_shared.ocr_render import is_text_pdf, open_document
from core.errors import ToolDomainError

MAX_ANALYZE_PAGES = 50
SAMPLE_ROWS = 3


def _span_rows(page_dict: dict) -> list[dict]:
    spans = []
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    spans.append({
                        "text": text,
                        "size": round(span.get("size", 0), 1),
                        "bold": bool(span.get("flags", 0) & 16),
                        "y": round(span.get("bbox", [0, 0, 0, 0])[1], 1),
                    })
    return spans


def _analyze_page(page, page_number: int) -> dict:
    info: dict = {"page": page_number,
                  "width": round(page.rect.width, 1),
                  "height": round(page.rect.height, 1)}
    page_dict = page.get_text("dict")
    spans = _span_rows(page_dict)
    if spans:
        sizes = sorted(s["size"] for s in spans)
        median = sizes[len(sizes) // 2]
        info["headers"] = [s["text"] for s in spans
                           if (s["size"] >= median * 1.25 or s["bold"])
                           and s["y"] < info["height"] * 0.35][:10]
        info["field_labels"] = [s["text"] for s in spans
                                if s["text"].endswith(("：", ":")) and len(s["text"]) <= 20][:15]

    tables = []
    try:
        found = page.find_tables()
        for table in found.tables:
            rows = table.extract()
            tables.append({
                "bbox": [round(v, 1) for v in table.bbox],
                "row_count": len(rows),
                "col_count": max((len(r) for r in rows), default=0),
                "header_row": [str(c or "").strip() for c in rows[0]] if rows else [],
                "sample_rows": [[str(c or "").strip()[:24] for c in row]
                                for row in rows[1:1 + SAMPLE_ROWS]],
            })
    except Exception:
        pass
    info["tables"] = tables[:8]
    return info


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ToolDomainError("布局分析仅支持 PDF（图片样例请走 spec.gen.vl 多模态方案）")

    text_pdf = is_text_pdf(path)
    doc = open_document(path)
    try:
        total = doc.page_count
        analyze_count = min(total, int(input.get("max_pages") or MAX_ANALYZE_PAGES))
        pages = []
        for index in range(analyze_count):
            pages.append(_analyze_page(doc.load_page(index), index + 1))
            if (index + 1) % 10 == 0:
                emit({"type": "progress", "phase": "analyze",
                      "message": f"已分析 {index + 1}/{analyze_count} 页"})
    finally:
        doc.close()

    layout = {
        "file": str(path),
        "is_text_pdf": text_pdf,
        "page_count": total,
        "analyzed_pages": len(pages),
        "pages": pages,
    }
    return {"layout": layout, "layout_json": json.dumps(layout, ensure_ascii=False)}
