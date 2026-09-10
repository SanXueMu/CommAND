"""OCR 结果库 SQLite 读写（CommOCR storage.py 移植）。

表结构（与 CommOCR 完全一致，ocrdb.extract.units / CommOCR 双向兼容）：
    meta(key TEXT PRIMARY KEY, value TEXT)
    records(file_hash TEXT, source_path TEXT, row_number INTEGER,
            page_number INTEGER, data TEXT/*JSON*/ )
缓存键 = (file_hash, source_path, row_number)——同文件同路径重跑跳过已存行。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def connect(db_path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS records (
            file_hash TEXT NOT NULL,
            source_path TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (file_hash, source_path, row_number)
        );
        """
    )
    connection.commit()


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    connection.commit()


def get_cached_rows(connection: sqlite3.Connection, file_hash: str, source_path: str) -> dict[int, list[dict]]:
    rows: dict[int, list[dict]] = {}
    cursor = connection.execute(
        "SELECT row_number, page_number, data FROM records "
        "WHERE file_hash = ? AND source_path = ? ORDER BY row_number",
        (file_hash, source_path),
    )
    for row in cursor:
        rows[row["row_number"]] = {
            "data": json.loads(row["data"]),
            "page_number": row["page_number"],
        }
    return rows


def append_records(connection: sqlite3.Connection, file_hash: str, source_path: str,
                   records: list[tuple[int, dict]]) -> int:
    """追加 (row_number, record) 序列（record 内含 页码 键）。返回真实新增条数。

    OR IGNORE 首写为准：断点重跑不覆盖已识别内容。
    """
    payload = [
        (file_hash, source_path, row_number, record.get("页码", 0),
         json.dumps(record, ensure_ascii=False))
        for row_number, record in records
    ]
    cursor = connection.executemany(
        "INSERT OR IGNORE INTO records(file_hash, source_path, row_number, page_number, data) "
        "VALUES(?, ?, ?, ?, ?)",
        payload,
    )
    connection.commit()
    return cursor.rowcount if cursor.rowcount >= 0 else 0


def read_records(connection: sqlite3.Connection,
                 file_hash: str | None = None, source_path: str | None = None) -> list[dict]:
    """读取记录（data JSON 展开 + 页码/行号提升；条件可选）。"""
    sql = "SELECT file_hash, source_path, row_number, page_number, data FROM records"
    conditions, params = [], []
    if file_hash:
        conditions.append("file_hash = ?")
        params.append(file_hash)
    if source_path:
        conditions.append("source_path = ?")
        params.append(source_path)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY source_path, file_hash, row_number"
    out = []
    for row in connection.execute(sql, params):
        record = json.loads(row["data"])
        record.setdefault("页码", row["page_number"])
        record["行号"] = row["row_number"]
        out.append(record)
    return out
