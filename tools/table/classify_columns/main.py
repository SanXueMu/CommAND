"""单元组 → 逐列分类 + 可译段收割（translee classify 移植，零翻译语义）。

- skip 列：整列命中数值/日期/编号模式（无需翻译，原样保留）
- 枚举列：唯一值 ≤ enum_max；文本列：其余
- 收割顺序契约见 command_shared/table.py（backfill 回查共用）
"""
from __future__ import annotations

import re

from command_shared.table import (
    DEFAULT_ENUM_MAX,
    DEFAULT_SKIP_RE,
    classify_columns,
    harvest_units,
)


def run(input: dict, ctx, emit) -> dict:
    units = input["units"]
    pattern = re.compile(input.get("skip_pattern") or DEFAULT_SKIP_RE)
    enum_max = int(input.get("enum_max") or DEFAULT_ENUM_MAX)

    col_classes = {
        unit["unit_id"]: (
            classify_columns(unit["rows"], pattern, enum_max)
            if unit.get("unit_type") == "table"
            else []
        )
        for unit in units
    }
    harvested = harvest_units(units, col_classes)

    counts = {}
    for unit in units:
        if unit.get("unit_type") == "table":
            c = col_classes[unit["unit_id"]]
            counts[unit["unit_id"]] = {
                "skip": sum(1 for x in c if x["class"] == "skip"),
                "enum": sum(1 for x in c if x["class"] == "enum"),
                "text": sum(1 for x in c if x["class"] == "text"),
            }
    emit({"phase": "classified", "segments": len(harvested["segments"]), "columns": counts})
    return {
        "col_classes": col_classes,
        "segments": harvested["segments"],
        "ranges": harvested["ranges"],
    }
