"""译文回插原表 → 中文版 xlsx（translee backfill xlsx 半边移植，纯数据 join）。

对齐链：单元 → ranges.start → unit_cells 收割序 → index_map → unique 下标 → 译文。
对应关系全部来自显式输入数据（零隐式共享知识）；review 格保留原文加 ⚠️ 前缀。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from command_shared.table import unit_cells

_REVIEW_PREFIX = "⚠️ "
_SHEET_UNSAFE_RE = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet_title(title: str) -> str:
    return _SHEET_UNSAFE_RE.sub("_", title)[:31] or "Sheet"


def _cell_result_map(unit: dict, col_classes: list[dict], start: int,
                     index_map: list[int], date_maps: list[dict],
                     translations: list[str], statuses: list[str]) -> dict[tuple[int, int], dict]:
    """单元 → {(row, col): {final, status}}（收割序与 classify 逐位一致）。"""
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


def _render_row(row: list[str], cell_map: dict[tuple[int, int], dict], row_idx: int) -> list[str]:
    out = []
    for col, cell in enumerate(row):
        entry = cell_map.get((row_idx, col))
        if entry is None:
            out.append(cell)
        elif entry["status"] == "ok":
            out.append(entry["final"])
        else:
            out.append(_REVIEW_PREFIX + cell)
    return out


def run(input: dict, ctx, emit) -> dict:
    from openpyxl import Workbook

    units = input["units"]
    col_classes = input["col_classes"]
    range_by_unit = {r["unit_id"]: r for r in input["ranges"]}
    segments = input["segments"]
    index_map = input["index_map"]
    date_maps = input["date_maps"]
    translations = input["translations"]
    statuses = input["statuses"]

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / ctx.handle
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(input["file"]).stem if input.get("file") else "output"
    out_name = input.get("out_name") or f"{stem}_中文版.xlsx"
    out_path = out_dir / out_name

    wb = Workbook(write_only=True)
    dict_rows: list[tuple[str, str, str, int]] = []
    seen_titles: set[str] = set()
    for unit in units:
        if unit.get("unit_type") != "table":
            continue
        unit_id = unit["unit_id"]
        rng = range_by_unit.get(unit_id)
        if rng is None:
            continue
        cell_map = _cell_result_map(unit, col_classes.get(unit_id, []), rng["start"],
                                    index_map, date_maps, translations, statuses)
        rows = unit["rows"]

        title = _safe_sheet_title(unit_id)
        n = 2
        while title in seen_titles:
            title = f"{_safe_sheet_title(unit_id)[:28]}_{n}"
            n += 1
        seen_titles.add(title)
        ws = wb.create_sheet(title)
        for row_idx, row in enumerate(rows):
            ws.append(_render_row(row, cell_map, row_idx))

        # 对照字典：收割序逐段（原文采样 + 回插后终译 + 状态 + 引用次数）
        counts: dict[int, int] = {}
        for g in index_map:
            counts[g] = counts.get(g, 0) + 1
        for j in range(rng["count"]):
            g = rng["start"] + j
            u = index_map[g]
            final = translations[u]
            for placeholder, value in date_maps[g].items():
                final = final.replace(placeholder, value)
            dict_rows.append((segments[g], final, statuses[u], counts[u]))

    ws_dict = wb.create_sheet("对照字典")
    ws_dict.append(["原文（日期归一前采样）", "译文", "状态", "引用次数"])
    for sample, translated, status, count in sorted(dict_rows, key=lambda r: -r[3]):
        ws_dict.append([sample, translated, status, count])

    wb.save(out_path)
    emit({"phase": "backfilled", "path": str(out_path), "dict_rows": len(dict_rows)})
    return {"path": str(out_path), "name": out_name, "dict_rows": len(dict_rows)}
