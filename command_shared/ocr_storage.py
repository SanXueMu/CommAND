"""OCR 结果库 SQLite 读写（CommOCR storage.py 移植）。

表结构（2026-09-20 AE 起主键含页内序 seq，一页可存多条分录）：
    meta(key TEXT PRIMARY KEY, value TEXT)
    records(file_hash TEXT, source_path TEXT, row_number INTEGER/*页序*/,
            seq INTEGER/*页内序 0..n-1*/, page_number INTEGER,
            data TEXT/*JSON*/, PRIMARY KEY (file_hash, source_path, row_number, seq))
旧库（主键无 seq）首次 initialize 自动迁移（建新表拷数据改名，旧行 seq=0）。
写入为页级替换语义：append 时先删同页旧行再插全量（失败页重跑/record 模式覆盖均正确）。
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
            seq INTEGER NOT NULL DEFAULT 0,
            page_number INTEGER NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (file_hash, source_path, row_number, seq)
        );
        """
    )
    _migrate_legacy_records(connection)
    connection.commit()


def _migrate_legacy_records(connection: sqlite3.Connection) -> None:
    """旧库（records 主键无 seq）自动迁移：建新表 → 拷数据（seq=0）→ 改名。

    旧库每页至多一行（OR IGNORE 时代只留第一条），seq=0 语义无损。
    """
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(records)")]
    if "seq" in columns:
        return
    # 只迁移已知旧 schema（五列齐备）；外来精简表（如测试桩）不动，读取侧照常工作
    legacy = {"file_hash", "source_path", "row_number", "page_number", "data"}
    if not legacy.issubset(columns):
        return
    connection.executescript(
        """
        BEGIN;
        CREATE TABLE records_new (
            file_hash TEXT NOT NULL,
            source_path TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            seq INTEGER NOT NULL DEFAULT 0,
            page_number INTEGER NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (file_hash, source_path, row_number, seq)
        );
        INSERT INTO records_new(file_hash, source_path, row_number, seq, page_number, data)
            SELECT file_hash, source_path, row_number, 0, page_number, data FROM records;
        DROP TABLE records;
        ALTER TABLE records_new RENAME TO records;
        COMMIT;
        """
    )


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
        "SELECT row_number, page_number, seq, data FROM records "
        "WHERE file_hash = ? AND source_path = ? ORDER BY row_number, seq",
        (file_hash, source_path),
    )
    for row in cursor:
        rows.setdefault(row["row_number"], []).append(
            {"data": json.loads(row["data"]), "page_number": row["page_number"]})
    return rows


def append_records(connection: sqlite3.Connection, file_hash: str, source_path: str,
                   records: list[tuple[int, dict]]) -> int:
    """追加 (row_number, record) 序列（record 内含 页码 键）。返回本次入库条数。

    页级替换语义（AE2）：同 row_number 已有旧行先删再插——失败页重跑覆盖旧内容、
    record 模式整文件覆盖、write_records 全新行号不受影响。页内序 seq 按入参顺序编 0..n-1。
    """
    page_numbers = sorted({row_number for row_number, _ in records})
    connection.executemany(
        "DELETE FROM records WHERE file_hash = ? AND source_path = ? AND row_number = ?",
        [(file_hash, source_path, rn) for rn in page_numbers],
    )
    seq_by_page: dict[int, int] = {}
    payload = []
    for row_number, record in records:
        seq = seq_by_page.get(row_number, 0)
        seq_by_page[row_number] = seq + 1
        payload.append((file_hash, source_path, row_number, seq,
                        record.get("页码", 0),
                        json.dumps(record, ensure_ascii=False)))
    cursor = connection.executemany(
        "INSERT INTO records(file_hash, source_path, row_number, seq, page_number, data) "
        "VALUES(?, ?, ?, ?, ?, ?)",
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
    sql += " ORDER BY source_path, file_hash, row_number, seq"
    out = []
    for row in connection.execute(sql, params):
        record = json.loads(row["data"])
        record.setdefault("页码", row["page_number"])
        record["行号"] = row["row_number"]
        out.append(record)
    return out
