"""单元组 × 译文 → 中文翻译 docx（translee backfill docx 半边移植，纯渲染）。

pdf 按页分隔（灰色页码条）+ 章节标题导航（译文段落启发识别 H2）+
表格还原（复用 xlsx 回填的列分类与逐格渲染）；review 单元加提示条。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from command_shared.table import unit_cells

_REVIEW_PREFIX = "⚠️ "

_H2_NUM_RE = re.compile(r"^\d{1,3}(\.\d+)*[.、．]\s*\S")
_H2_KEYWORDS = ("引言", "概述", "背景", "范围", "目的", "总结", "结论", "附件")


def _is_heading2(text: str) -> bool:
    """章节标题启发（作用于译文段落）：编号行 / 白名单短行 / 全大写短行。"""
    t = text.strip()
    if not t or len(t) > 60 or t.endswith(("。", "，", "；", ";", ",")):
        return False
    if _H2_NUM_RE.match(t):
        return True
    if any(t.startswith(k) and len(t) <= 12 for k in _H2_KEYWORDS):
        return True
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 4 and " " in t and all(c.isupper() for c in letters)


def _table_cell_map(unit: dict, col_classes: list[dict], start: int,
                    index_map, date_maps, translations, statuses) -> dict[tuple[int, int], dict]:
    result: dict[tuple[int, int], dict] = {}
    rows = unit["rows"]
    for j, (row_idx, col_idx) in enumerate(unit_cells(rows, col_classes)):
        g = start + j
        u = index_map[g]
        entry = {"status": statuses[u], "dates": date_maps[g]}
        if statuses[u] == "ok":
            final = translations[u]
            for placeholder, value in entry["dates"].items():
                final = final.replace(placeholder, value)
            entry["final"] = final
        result[(row_idx, col_idx)] = entry
    return result


def run(input: dict, ctx, emit) -> dict:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    units = input["units"]
    range_by_unit = {r["unit_id"]: r for r in input["ranges"]}
    index_map = input["index_map"]
    date_maps = input["date_maps"]
    translations = input["translations"]
    statuses = input["statuses"]
    col_classes = input.get("col_classes") or {}
    segments = input.get("segments")

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / ctx.handle
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(input["file"]).stem if input.get("file") else "output"
    out_name = input.get("out_name") or f"{stem}_中文翻译.docx"
    out_path = out_dir / out_name

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.element.rPr.rFonts.set(qn("w:eastAsia"), "等线")
    doc.add_heading(f"{stem} 中文翻译", 0)
    meta_p = doc.add_paragraph()
    run = meta_p.add_run(
        f"来源：{input.get('file') or ''} · 生成时间：{datetime.now():%Y-%m-%d %H:%M}"
    )
    run.font.size = Pt(9)

    for unit in units:
        rng = range_by_unit.get(unit["unit_id"])
        if rng is None:
            continue
        if unit.get("unit_type") == "table":
            cell_map = _table_cell_map(unit, col_classes.get(unit["unit_id"], []),
                                       rng["start"], index_map, date_maps, translations, statuses)
            rows = unit["rows"]
            ncols = max(len(r) for r in rows) or 1
            table = doc.add_table(rows=len(rows), cols=ncols)
            try:
                table.style = "Table Grid"
            except KeyError:
                pass
            for i, row in enumerate(rows):
                for j in range(ncols):
                    entry = cell_map.get((i, j))
                    if entry is None:
                        text = row[j] if j < len(row) else ""
                    elif entry["status"] == "ok":
                        text = entry["final"]
                    else:
                        text = _REVIEW_PREFIX + (row[j] if j < len(row) else "")
                    cell = table.cell(i, j)
                    cell.text = text
                    if i == 0:
                        for p in cell.paragraphs:
                            for r in p.runs:
                                r.font.bold = True
            continue

        # text 单元：整段一条
        g = rng["start"]
        u = index_map[g]
        translated = translations[u]
        status = statuses[u]
        text = unit.get("text", "")
        page = (unit.get("meta") or {}).get("page")
        label = f"第 {page} 页" if page else unit["unit_id"]
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        marker = p.add_run(f"— {label} —")
        marker.font.size = Pt(9)
        marker.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        if status != "ok" or (not translated and text):
            doc.add_paragraph("⚠️ 本单元质检未过，以下译文仅供参考")
        content = translated or text or ""
        for para in content.split("\n"):
            para = para.strip()
            if not para:
                doc.add_paragraph("")
            elif _is_heading2(para):
                doc.add_heading(para, level=2)
            else:
                doc.add_paragraph(para)

    doc.save(out_path)
    emit({"phase": "rendered", "path": str(out_path)})
    return {"path": str(out_path), "name": out_name}
