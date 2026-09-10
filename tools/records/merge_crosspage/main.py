"""跨页记录合并（records → records，纯函数）。

两种模式（可叠加顺序执行）：
- join：键字段为空/缺席的续行并入上一条记录（非空字段以 sep 连接）——明细续页
- fill：键字段非空行之后的空键行继承键值——标题行跨页（决算表场景）
"""
from __future__ import annotations

from core.errors import ToolDomainError

ABSENT = ("", "未见", "未出现")


def _is_blank(value) -> bool:
    return str(value or "").strip() in ABSENT


def _join(records, key_field: str, sep: str) -> list[dict]:
    out: list[dict] = []
    for record in records:
        row = dict(record)
        if out and _is_blank(row.get(key_field)):
            prev = out[-1]
            for field, value in row.items():
                if field in ("页码", "行号") or field == key_field:
                    continue
                text = str(value or "").strip()
                if text and text not in ABSENT:
                    prev[field] = f"{prev.get(field, '')}{sep}{text}" if prev.get(field) else text
        else:
            out.append(row)
    return out


def _fill(records, key_field: str) -> list[dict]:
    out = []
    current = None
    for record in records:
        row = dict(record)
        value = str(row.get(key_field) or "").strip()
        if value and value not in ABSENT:
            current = value
        elif current is not None:
            row[key_field] = current
        out.append(row)
    return out


def run(input: dict, ctx, emit) -> dict:
    records = input["records"]
    if not isinstance(records, list) or not records:
        raise ToolDomainError("records 必须为非空数组")
    key_field = input["key_field"]
    modes = input.get("modes") or ["join"]
    sep = input.get("sep") or "；"

    merged = records
    for mode in modes:
        if mode == "join":
            merged = _join(merged, key_field, sep)
        elif mode == "fill":
            merged = _fill(merged, key_field)
        else:
            raise ToolDomainError(f"未知合并模式: {mode}（可选 join/fill）")

    emit({"type": "progress", "phase": "merge",
          "message": f"{len(records)} 条 → {len(merged)} 条（{','.join(modes)}）"})
    return {"records": merged, "records_count": len(merged),
            "merged_from": len(records), "key_field": key_field}
