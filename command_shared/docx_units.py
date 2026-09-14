"""docx → 通用单元组（与 pdf/xlsx 链共用的 units 契约）。

顺序契约（提取与回填必须逐位一致，故收敛于此共享模块）：
- 按 `document.element.body` 子元素顺序遍历，段落与表格**交错保序**（正文流真实顺序）
- 段落 → `{"unit_id": "p{i}", "unit_type": "text", "text": ...}`（一段一条，与 harvest_units 一致）
- 表格 → `{"unit_id": "t{i}", "unit_type": "table", "rows": [[...]]}`（首行视为表头，同 classify 契约）
- `meta.body_index` 为元素在 body 中的序号，回填据此定位；`meta.style/heading` 供对照渲染复用样式

跳过（不产出单元，回填时原样保留）：
- 空段落 / 纯数字·标点段落（默认开启，省 token）
- 含域代码（fldChar/instrText/fldSimple）与目录（TOC 样式）的段落——回填会破坏 Word 域
- 页眉页脚、文本框、批注、脚注/尾注不在 body 内，天然不参与（已知上限）
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from docx.oxml.ns import qn

_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_FIELD_TAGS = ("w:fldChar", "w:instrText", "w:fldSimple")
_TOC_PREFIXES = ("TOC", "目录")
_HEADING_RE = re.compile(r"^(?:Heading|标题)\s*(\d)")


def iter_body(document: Any) -> Iterator[tuple[int, str, Any]]:
    """按 body 顺序产出 `(body_index, kind, obj)`，kind ∈ {"p", "tbl"}。"""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for index, child in enumerate(document.element.body.iterchildren()):
        if child.tag == qn("w:p"):
            yield index, "p", Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield index, "tbl", Table(child, document)


def unit_id_of(index: int, kind: str) -> str:
    return f"p{index}" if kind == "p" else f"t{index}"


def body_index_map(document: Any) -> dict[str, Any]:
    """`unit_id` → body 元素对象（段落/表格），供回填按单元定位。"""
    return {unit_id_of(i, kind): obj for i, kind, obj in iter_body(document)}


def paragraph_text(paragraph: Any) -> str:
    return (paragraph.text or "").strip()


def style_name(paragraph: Any) -> str | None:
    try:
        return paragraph.style.name if paragraph.style is not None else None
    except Exception:  # noqa: BLE001 样式缺失/异常样式名不致命
        return None


def heading_level(paragraph: Any) -> int | None:
    match = _HEADING_RE.match(style_name(paragraph) or "")
    return int(match.group(1)) if match else None


def is_field_paragraph(paragraph: Any) -> bool:
    """含域代码（页码/交叉引用/公式域等）——回填会破坏域，跳过。"""
    element = paragraph._p  # noqa: SLF001 python-docx 标准取法
    return any(element.findall(f".//{qn(tag)}") for tag in _FIELD_TAGS)


def is_toc_paragraph(paragraph: Any) -> bool:
    name = style_name(paragraph) or ""
    return name.upper().startswith("TOC") or name.startswith("目录")


def table_rows(table: Any) -> list[list[str]]:
    """表格 → 逐格文本（合并单元格按 python-docx 语义重复出现）。"""
    return [[(cell.text or "").strip() for cell in row.cells] for row in table.rows]


def _rows_have_text(rows: list[list[str]]) -> bool:
    return any(_LETTER_RE.search(cell) for row in rows for cell in row)


def extract_units(document: Any, include_tables: bool = True,
                  skip_numbers: bool = True) -> dict[str, Any]:
    """docx 文档 → `{"units": [...], "stats": {...}}`（units 契约同 pdf/xlsx 链）。"""
    from command_shared.table import DEFAULT_SKIP_RE, is_skippable

    skip_re = re.compile(DEFAULT_SKIP_RE)
    units: list[dict[str, Any]] = []
    stats = {"paragraphs": 0, "tables": 0, "skipped_empty": 0, "skipped_number": 0,
             "skipped_field": 0, "text_chars": 0}
    for index, kind, obj in iter_body(document):
        if kind == "tbl":
            stats["tables"] += 1
            if not include_tables:
                continue
            rows = table_rows(obj)
            if not rows or not _rows_have_text(rows):
                stats["skipped_empty"] += 1
                continue
            units.append({"unit_id": unit_id_of(index, kind), "unit_type": "table", "rows": rows,
                          "meta": {"body_index": index, "rows": len(rows),
                                   "cols": max((len(r) for r in rows), default=0)}})
            stats["text_chars"] += sum(len(cell) for row in rows for cell in row)
            continue

        stats["paragraphs"] += 1
        text = paragraph_text(obj)
        if not text:
            stats["skipped_empty"] += 1
            continue
        if is_field_paragraph(obj) or is_toc_paragraph(obj):
            stats["skipped_field"] += 1
            continue
        if skip_numbers and is_skippable(text, skip_re):
            stats["skipped_number"] += 1
            continue
        units.append({"unit_id": unit_id_of(index, kind), "unit_type": "text", "text": text,
                      "meta": {"body_index": index, "style": style_name(obj),
                               "heading": heading_level(obj)}})
        stats["text_chars"] += len(text)

    stats["units"] = len(units)
    return {"units": units, "stats": stats}
