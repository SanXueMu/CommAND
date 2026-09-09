"""commOcr 结果库 → 每来源一个 table 单元；长值独立 text 单元（translee extract_ocr_db 移植）。

records 表结构：source_path / page_number / data(JSON: 字段→值)。
短值进「字段 | 值」两列表格批翻；长值（> long_value_chars，如合同条款）
独立成 text 单元整篇翻译，unit_id 含来源/字段/页码。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {path}")
    long_value_chars = int(input.get("long_value_chars", 200))

    table_units: dict[str, dict] = {}
    text_units: list[dict] = []
    seen_ids: set[str] = set()
    with sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "SELECT source_path, page_number, data FROM records ORDER BY source_path, page_number"
        )
        for source_path, page_number, data_json in cursor:
            unit = table_units.setdefault(source_path, {
                "unit_id": Path(source_path).name,
                "unit_type": "table",
                "rows": [["字段 (页码)", "值"]],
            })
            try:
                data = json.loads(data_json)
            except (TypeError, json.JSONDecodeError):
                data = {}
            unit["rows"].append([str(page_number), ""])
            for key, value in data.items():
                text = _format_cell(value)
                if len(text) > long_value_chars:
                    uid = f"{Path(source_path).name}·{key}·p{page_number}"
                    n = 2
                    while uid in seen_ids:
                        uid = f"{Path(source_path).name}·{key}·p{page_number}#{n}"
                        n += 1
                    seen_ids.add(uid)
                    text_units.append({
                        "unit_id": uid, "unit_type": "text", "text": text,
                    })
                else:
                    unit["rows"].append([f"{key} (p{page_number})", text])

    units = list(table_units.values()) + text_units
    emit({"phase": "extracted", "units": len(units)})
    return {"file": str(path), "file_hash": _file_hash(path), "kind": "ocr_db", "units": units}
