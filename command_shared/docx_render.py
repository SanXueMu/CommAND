"""docx 译文回填（overlay 原位覆盖 / bilingual 段落对照）。

顺序契约（与 `command_shared.table.harvest_units` 逐位一致，故回填可确定对齐）：
- text 单元：整段一条 → 全局段号 = `range.start`（count 恒为 1）
- table 单元：表头字母格在前 + 数据行行主序（仅非 skip 列非空格）→ 与 `unit_cells` 同序

改写策略：
- overlay：仅改有译文的段落/单元格——写入首个文本 run 并清空其余文本 run，保留含图片/对象的
  run、段落样式、表格边框底纹；域代码/目录段落不在单元组内，天然不动
- bilingual：原文原样保留，其后插入译文段（复用标题样式，深蓝字），表格在单元格内另起一段
- 质检未过（status != ok）默认仍写回机器译文（保证可读），bilingual 下加 ⚠️ 前缀标记
- `index_map/statuses/date_maps` 可为 None（可选参数可空口径）：None 时按全局段号直取
"""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn

from command_shared.docx_units import body_index_map, heading_level
from command_shared.table import unit_cells

TRANSLATION_RGB = (0x1F, 0x4E, 0x79)  # 深蓝：与 PDF 双语对照栏同色系
REVIEW_PREFIX = "⚠️ "


def _resolve(seg_index: int, index_map: list[int] | None, date_maps: list[dict] | None,
             translations: list[str] | None, statuses: list[str] | None) -> tuple[str | None, str]:
    """全局段号 → (译文, 质检状态)；无译文返回 (None, 原因)。"""
    unique = index_map[seg_index] if index_map and seg_index < len(index_map) else seg_index
    if unique is None or unique < 0 or not translations or unique >= len(translations):
        return None, "missing"
    text = translations[unique] or ""
    if not text.strip():
        return None, "empty"
    status = statuses[unique] if statuses and unique < len(statuses) else "ok"
    status = status or "ok"
    dates = date_maps[seg_index] if date_maps and seg_index < len(date_maps) else None
    for placeholder, value in (dates or {}).items():
        text = text.replace(placeholder, value)
    return text, status


def table_cell_translations(unit: dict, col_classes: list[dict], start: int,
                            index_map, date_maps, translations,
                            statuses) -> dict[tuple[int, int], tuple[str, str]]:
    """表格单元 → `{(row, col): (译文, 状态)}`（收割序与 harvest_units 完全一致）。"""
    result: dict[tuple[int, int], tuple[str, str]] = {}
    rows = unit.get("rows") or []
    for offset, (row_idx, col_idx) in enumerate(unit_cells(rows, col_classes)):
        text, status = _resolve(start + offset, index_map, date_maps, translations, statuses)
        if text is not None:
            result[(row_idx, col_idx)] = (text, status)
    return result


def set_paragraph_text(paragraph: Any, text: str) -> None:
    """整段替换文本：写入首个文本 run，清空其余文本 run。

    保留含图片/对象的 run（只清有文字的 run）与段落样式；
    超链接内的 run 属 `w:hyperlink` 子元素，一并清空文本（链接关系与 URL 保留，避免半中半英）。
    """
    runs = list(paragraph.runs)
    text_runs = [r for r in runs if (r.text or "").strip()]
    if text_runs:
        text_runs[0].text = text
        for run in text_runs[1:]:
            run.text = ""
    elif runs:
        runs[0].text = text
    else:
        paragraph.add_run(text)
    for node in paragraph._p.findall(f".//{qn('w:hyperlink')}//{qn('w:t')}"):  # noqa: SLF001
        node.text = ""


def _insert_after(document: Any, anchor: Any, text: str, status: str,
                  source_style_level: int | None, mark_review: bool) -> None:
    """在 anchor 段之后插入译文段（复用标题样式；深蓝）。"""
    from docx.shared import RGBColor

    paragraph = document.add_paragraph()
    if source_style_level is not None:
        name = f"Heading {source_style_level}"
        try:
            paragraph.style = document.styles[name]
        except KeyError:
            pass
    prefix = REVIEW_PREFIX if (mark_review and status != "ok") else ""
    run = paragraph.add_run(prefix + text)
    run.font.color.rgb = RGBColor(*TRANSLATION_RGB)
    anchor._p.addnext(paragraph._p)  # noqa: SLF001 末尾新建后搬到源段之后


def _write_cell(cell: Any, text: str, status: str, mode: str, mark_review: bool,
                stats: dict[str, int]) -> None:
    if mode == "overlay":
        paragraphs = cell.paragraphs
        if paragraphs:
            set_paragraph_text(paragraphs[0], text)
            for extra in paragraphs[1:]:  # 单元格内多余段落清空，保持结构
                set_paragraph_text(extra, "")
        else:  # pragma: no cover 空单元格极少见
            cell.text = text
        stats["replaced"] += 1
        return
    from docx.shared import RGBColor

    paragraph = cell.add_paragraph()
    prefix = REVIEW_PREFIX if (mark_review and status != "ok") else ""
    run = paragraph.add_run(prefix + text)
    run.font.color.rgb = RGBColor(*TRANSLATION_RGB)
    stats["inserted"] += 1


def build_document_from_units(units: list[dict]) -> tuple[Any, dict[str, Any]]:
    """源不是 docx（pdf/txt 文档翻译流）时：**按单元顺序新建文档** + 显式元素映射。

    关键点：pdf/txt 的 unit_id 自成体系（`pdf.extract.pages` 用 `"1"`/`"1T0"`、
    `txt.extract.text` 用文件名），**与 docx 的 `p{i}/t{i}`（body 序）不兼容**——
    所以不能靠 `body_index_map` 反查，必须把「我建的元素」按 unit_id 直接登记 ✓
    （2026-09-14 线上：文档翻译流产物为空 / IndexError 的根因）。
    """
    from docx import Document

    document = Document()
    element_map: dict[str, Any] = {}
    for unit in units or []:
        unit_id = unit.get("unit_id")
        if unit.get("unit_type") == "table":
            rows = [r for r in (unit.get("rows") or [])]
            if not rows:
                continue
            width = max((len(r) for r in rows), default=0)
            if not width:
                continue
            table = document.add_table(rows=len(rows), cols=width)
            for r, row in enumerate(rows):
                for c in range(width):
                    value = row[c] if c < len(row) else ""
                    table.rows[r].cells[c].text = "" if value is None else str(value)
            if unit_id is not None:
                element_map[str(unit_id)] = table
        else:
            paragraph = document.add_paragraph(unit.get("text") or "")
            if unit_id is not None:
                element_map[str(unit_id)] = paragraph
    return document, element_map


def render_document(document: Any, *, units: list[dict], ranges: list[dict] | None,
                    index_map: list[int] | None, date_maps: list[dict] | None,
                    translations: list[str] | None, statuses: list[str] | None,
                    col_classes: dict[str, list[dict]] | None = None,
                    mode: str = "bilingual", mark_review: bool = True,
                    element_map: dict[str, Any] | None = None) -> dict[str, int]:
    """按单元组回填译文（overlay 原位覆盖 / bilingual 段落对照），返回统计。

    element_map 缺省按 docx body 序（`p{i}/t{i}`）反查；源是 pdf/txt 时由
    `build_document_from_units` 传入显式映射（unit_id 体系不同）。
    """
    if mode not in ("overlay", "bilingual"):
        raise ValueError(f"未知渲染模式: {mode}")
    range_by_unit = {r["unit_id"]: r for r in (ranges or [])}
    element_map = element_map or body_index_map(document)
    stats = {"units": 0, "replaced": 0, "inserted": 0, "review": 0, "skipped": 0, "chars_out": 0}

    for unit in units or []:
        unit_id = unit.get("unit_id")
        rng = range_by_unit.get(unit_id)
        anchor = element_map.get(unit_id)
        if rng is None or anchor is None or int(rng.get("count") or 0) < 1:
            stats["skipped"] += 1
            continue
        start = int(rng.get("start") or 0)

        if unit.get("unit_type") == "table":
            classes = (col_classes or {}).get(unit_id, [])
            cell_map = table_cell_translations(unit, classes, start, index_map, date_maps,
                                              translations, statuses)
            if not cell_map:
                stats["skipped"] += 1
                continue
            stats["units"] += 1
            for (row_idx, col_idx), (text, status) in sorted(cell_map.items()):
                try:
                    cell = anchor.cell(row_idx, col_idx)
                except IndexError:  # pragma: no cover 合并单元格行列错位
                    stats["skipped"] += 1
                    continue
                _write_cell(cell, text, status, mode, mark_review, stats)
                stats["chars_out"] += len(text)
                if status != "ok":
                    stats["review"] += 1
            continue

        text, status = _resolve(start, index_map, date_maps, translations, statuses)
        if text is None:
            stats["skipped"] += 1
            continue
        stats["units"] += 1
        if mode == "overlay":
            set_paragraph_text(anchor, text)
            stats["replaced"] += 1
        else:
            _insert_after(document, anchor, text, status,
                          heading_level(anchor), mark_review)
            stats["inserted"] += 1
        stats["chars_out"] += len(text)
        if status != "ok":
            stats["review"] += 1
    return stats
