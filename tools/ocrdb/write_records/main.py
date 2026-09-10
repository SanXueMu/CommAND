"""结果库写入：records（任意来源）→ ocr_results.db（与 CommOCR/读工具同构）。

与 ocrdb.extract.units 成对偶；用于切块识别记录、跨页合并结果等外部记录落库。
file_hash 缺省按记录内容摘要生成（无源文件的纯数据写入）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from command_shared import ocr_storage
from core.errors import ToolDomainError


def run(input: dict, ctx, emit) -> dict:
    records = input["records"]
    if not isinstance(records, list) or not records:
        raise ToolDomainError("records 必须为非空数组")

    db_path = Path(input["db"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = input.get("source_path") or "records"
    file_hash = input.get("file_hash") or hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    existing = set()
    if db_path.exists():
        connection = ocr_storage.connect(db_path)
        try:
            ocr_storage.initialize(connection)
            existing = set(ocr_storage.get_cached_rows(connection, file_hash, source_path))
        finally:
            connection.close()

    connection = ocr_storage.connect(db_path)
    try:
        ocr_storage.initialize(connection)
        start = (max(existing) + 1) if existing else 1
        payload = []
        for offset, record in enumerate(records):
            row = dict(record)
            row.setdefault("页码", int(row.get("页码") or 1))
            payload.append((start + offset, row))
        written = ocr_storage.append_records(connection, file_hash, source_path, payload)
    finally:
        connection.close()

    emit({"type": "progress", "phase": "write",
          "message": f"写入 {written} 条记录 → {db_path.name}"})
    return {"db": str(db_path), "source_path": source_path,
            "file_hash": file_hash, "written": written}
