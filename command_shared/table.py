"""表格/文本单元的可译段收割（classify 与两类回填共用的确定性顺序）。

顺序契约（收割与回查必须逐位一致，故收敛于此共享模块）：
- table 单元：表头行（含字母/汉字的单元格）在前，数据行按行主序（仅非 skip 列非空格）
- text 单元：整段文本一条
"""

from __future__ import annotations

import re

# 列分类默认参数（工具可用输入参数覆盖，零耦合）
DEFAULT_SKIP_RE = r"^[\d\s/\-:.,()%¥$€£#&+＋]+$"
DEFAULT_ENUM_MAX = 100

_HEADER_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")


def is_skippable(value: str, pattern: re.Pattern) -> bool:
    """单元格是否无需翻译（纯数字/日期/编号/代码模式）。"""
    return bool(pattern.match(value))


def classify_columns(
    rows: list[list[str]], pattern: re.Pattern, enum_max: int = DEFAULT_ENUM_MAX
) -> list[dict]:
    """逐列分类（首行视为表头不参与列性判定）：skip / enum / text。"""
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    result = []
    for col in range(ncols):
        values = [r[col] for r in rows[1:] if col < len(r) and r[col].strip()]
        if not values or all(is_skippable(v, pattern) for v in values):
            result.append({"col": col, "class": "skip", "unique": len(set(values))})
            continue
        unique = len(set(values))
        result.append({"col": col, "class": "enum" if unique <= enum_max else "text", "unique": unique})
    return result


def unit_cells(rows: list[list[str]], col_classes: list[dict]) -> list[tuple[int, int]]:
    """表格单元 → 收割序 (row, col) 列表（表头字母格在前，数据行行主序）。"""
    translatable = {c["col"] for c in col_classes if c["class"] != "skip"}
    cells: list[tuple[int, int]] = []
    if rows:
        for col, cell in enumerate(rows[0]):
            if cell.strip() and _HEADER_LETTER_RE.search(cell):
                cells.append((0, col))
        for row_idx, row in enumerate(rows[1:], start=1):
            for col, cell in enumerate(row):
                if col in translatable and cell.strip():
                    cells.append((row_idx, col))
    return cells


def harvest_units(units: list[dict], col_classes_map: dict[str, list[dict]]) -> dict:
    """单元组 → 全局段落序列 + 各单元区间。

    返回 {"segments": [...], "ranges": [{"unit_id", "start", "count"}, ...]}（与 units 同序）。
    """
    segments: list[str] = []
    ranges: list[dict] = []
    for unit in units:
        start = len(segments)
        if unit.get("unit_type") == "table":
            rows = unit["rows"]
            col_classes = col_classes_map.get(unit["unit_id"], [])
            for row_idx, col_idx in unit_cells(rows, col_classes):
                segments.append(rows[row_idx][col_idx].strip())
        else:
            text = (unit.get("text") or "").strip()
            if text:
                segments.append(text)
        ranges.append({"unit_id": unit["unit_id"], "start": start, "count": len(segments) - start})
    return {"segments": segments, "ranges": ranges}
