"""版式感知的 PDF 块提取（供原位叠加 / 双语对照翻译）。

块 = 文字块（get_text("dict")）+ 表格块（find_tables），均带 bbox（PDF 点，左上原点）。
`flatten_blocks` 把块摊平成「可翻译片段」——文字块整块一段，表格块逐格一段——
渲染工具用同一函数重建顺序，保证 segment[i] 与 i 号片段一一对应。
"""
from __future__ import annotations


def _overlap_ratio(inner: list[float], outer: list[float]) -> float:
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    w = max(0.0, min(ix1, ox1) - max(ix0, ox0))
    h = max(0.0, min(iy1, oy1) - max(iy0, oy0))
    area = max(1e-6, (ix1 - ix0) * (iy1 - iy0))
    return (w * h) / area


def _reading_order(block: dict) -> tuple:
    x0, y0 = block["bbox"][0], block["bbox"][1]
    return (round(y0 / 8.0), round(x0 / 8.0))


def _text_blocks(page, table_boxes: list[list[float]]) -> list[dict]:
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:  # 0=文字块, 1=图片块（图片不参与翻译）
            continue
        lines = []
        for ln in b.get("lines", []):
            from command_shared.text_clean import xml_safe_text
            txt = xml_safe_text("".join(s.get("text", "") for s in ln.get("spans", []))).strip()
            if txt:
                lines.append({"bbox": list(ln.get("bbox") or b["bbox"]), "text": txt})
        text = "\n".join(l["text"] for l in lines).strip()
        if not text:
            continue
        bbox = list(b["bbox"])
        meta: dict = {}
        if any(_overlap_ratio(bbox, tb) >= 0.6 for tb in table_boxes):
            meta["in_table"] = True
        out.append({"type": "text", "bbox": bbox, "text": text, "lines": lines, "meta": meta})
    return out


def _table_blocks(page) -> list[dict]:
    try:
        found = page.find_tables()
        tables = getattr(found, "tables", None) or []
    except Exception:
        return []
    out = []
    for k, tab in enumerate(tables, start=1):
        try:
            data = [[(c or "").strip() for c in row] for row in tab.extract()]
        except Exception:
            continue
        rows = [r for r in data if any(x for x in r)]
        if not rows:
            continue
        out.append({"type": "table", "bbox": list(tab.bbox), "rows": data,
                    "cells": _table_cells(tab, data), "meta": {"table_index": k}})
    return out


def _table_cells(tab, data: list[list[str]]) -> list[dict]:
    """逐格 [(row, col, bbox, text)]，bbox 缺失时回退表格整体 bbox。"""
    cells = []
    trows = getattr(tab, "rows", None) or []
    for r, row in enumerate(trows):
        for c, cbox in enumerate(getattr(row, "cells", None) or []):
            if cbox is None:
                continue
            text = data[r][c] if r < len(data) and c < len(data[r]) else ""
            if text.strip():
                cells.append({"row": r, "col": c, "bbox": list(cbox), "text": text.strip()})
    if not cells:  # find_tables 无逐格 bbox 时，至少保留文本
        for r, row in enumerate(data):
            for c, text in enumerate(row):
                if text.strip():
                    cells.append({"row": r, "col": c, "bbox": list(tab.bbox), "text": text.strip()})
    return cells


def extract_blocks(doc, include_tables: bool = True) -> list[dict]:
    blocks: list[dict] = []
    for i, page in enumerate(doc, start=1):
        tables = _table_blocks(page) if include_tables else []
        tboxes = [t["bbox"] for t in tables]
        page_blocks = _text_blocks(page, tboxes) + tables
        page_blocks.sort(key=_reading_order)
        for n, b in enumerate(page_blocks, start=1):
            b["id"] = f"{i}.{n}"
            b["page"] = i
            b.setdefault("meta", {})
            blocks.append(b)
    return blocks


def flatten_blocks(blocks: list[dict]) -> list[dict]:
    """块 → 可翻译片段（与渲染端一一对应）。

    文字块 → 1 段（kind=text）；表格块 → 每格 1 段（kind=cell）。
    """
    items: list[dict] = []
    for b in blocks:
        if b.get("type") == "table":
            for c in b.get("cells") or []:
                items.append({
                    "block_id": b["id"], "page": b["page"], "kind": "cell",
                    "bbox": c["bbox"], "text": c["text"], "row": c["row"], "col": c["col"],
                })
        else:
            if b.get("meta", {}).get("in_table"):
                continue  # 表格内文字由 cell 片段负责，避免重复翻译
            items.append({
                "block_id": b["id"], "page": b["page"], "kind": "text",
                "bbox": b["bbox"], "text": b.get("text", ""),
            })
    for idx, it in enumerate(items):
        it["index"] = idx
    return items
