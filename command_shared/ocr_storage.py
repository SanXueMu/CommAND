"""OCR 结果库 SQLite 读写（CommOCR storage.py 移植）。

表结构（2026-09-20 AE 起主键含页内序 seq；2026-09-20 AP 起含识别指纹 fingerprint）：
    meta(key TEXT PRIMARY KEY, value TEXT)
    records(file_hash TEXT, source_path TEXT, row_number INTEGER/*页序*/,
            seq INTEGER/*页内序 0..n-1*/, page_number INTEGER,
            data TEXT/*JSON*/, fingerprint TEXT/*识别配置指纹*/,
            PRIMARY KEY (file_hash, source_path, row_number, seq))
旧库（主键无 seq）首次 initialize 自动迁移（建新表拷数据改名，旧行 seq=0）；
更旧库（无 fingerprint 列）自动 ALTER 补列（旧行 fingerprint=''）。
写入为页级替换语义：append 时先删同页旧行再插全量（失败页重跑/record 模式覆盖均正确）。

AP：**页级缓存以指纹为准**——只有「文件内容 + 来源名 + 识别配置指纹」三者都一致的行
才算命中；改模版/规则/钩子/模型后指纹变化 → 该文件全部页重新识别，不再回放旧结果。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

UPLOADS_DIR_NAME = "uploads"


def default_db_path(src) -> Path:
    """默认结果库路径：`<数据目录>/ocr/<本次上传标识>_<文件名>.ocr_results.db`。

    AP-C：标识取上传目录的 uuid8（批量上传时 uuid8 在**目录**上、文件名不含它），
    于是**同一次上传**的重跑仍命中页级缓存（省钱），不同批次/重传各自独立成库——
    不再跨批次共享（删除不再被别的批次挡住、也不会吃到别的上传的旧缓存）。
    单文件上传的文件名自带 uuid8 前缀时不重复加；不在 uploads 下的路径退化为路径哈希
    （同一路径稳定，重跑仍可命中）。
    """
    src = Path(src)
    ident = upload_identity(src)
    stem = src.stem
    name = stem if (not ident or stem.startswith(f"{ident}_")) else f"{ident}_{stem}"
    return Path(os.environ.get("COMMAND_DATA_DIR", "data")) / "ocr" / f"{name}.ocr_results.db"


def upload_identity(src) -> str:
    """本次上传的标识：uploads/<日期>/<uuid8>_<根> 的 uuid8，其次文件名前缀，最后路径哈希。"""
    path = Path(src)
    parts = path.parts
    if UPLOADS_DIR_NAME in parts:
        index = parts.index(UPLOADS_DIR_NAME)
        if len(parts) > index + 2:
            match = re.match(r"([0-9a-f]{8})_", parts[index + 2])
            if match:
                return match.group(1)
    match = re.match(r"([0-9a-f]{8})_", path.name)
    if match:
        return match.group(1)
    return hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:8]


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
            fingerprint TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (file_hash, source_path, row_number, seq)
        );
        """
    )
    _migrate_legacy_records(connection)
    _ensure_fingerprint_column(connection)
    connection.commit()


def _ensure_fingerprint_column(connection: sqlite3.Connection) -> None:
    """旧库补 fingerprint 列（ALTER 可原地加列；旧行 '' → 与任何新指纹都不匹配，
    等价于「下次重跑重新识别一次」，正是 AP 想要的语义）。"""
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(records)")]
    if not columns or "fingerprint" in columns:
        return
    connection.execute("ALTER TABLE records ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")


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
            fingerprint TEXT NOT NULL DEFAULT '',
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


def get_cached_rows(connection: sqlite3.Connection, file_hash: str, source_path: str,
                    fingerprint: str | None = None) -> dict[int, list[dict]]:
    """已入库行（按页序分组）。

    AP：给了 `fingerprint` 时只认**指纹一致**的行（改模版/规则/钩子/模型后自动失效）；
    不传（旧调用/工具内省）则返回全部，保持兼容。
    """
    rows: dict[int, list[dict]] = {}
    sql = ("SELECT row_number, page_number, seq, data FROM records "
           "WHERE file_hash = ? AND source_path = ?")
    params: list = [file_hash, source_path]
    if fingerprint is not None:
        sql += " AND fingerprint = ?"
        params.append(fingerprint)
    cursor = connection.execute(sql + " ORDER BY row_number, seq", params)
    for row in cursor:
        rows.setdefault(row["row_number"], []).append(
            {"data": json.loads(row["data"]), "page_number": row["page_number"]})
    return rows


def delete_file_rows(connection: sqlite3.Connection, file_hash: str, source_path: str) -> int:
    """清掉该文件（内容哈希 + 来源名）的全部行——「强制重新识别」用。返回删除条数。"""
    cursor = connection.execute(
        "DELETE FROM records WHERE file_hash = ? AND source_path = ?",
        (file_hash, source_path),
    )
    connection.commit()
    return cursor.rowcount if cursor.rowcount >= 0 else 0


def append_records(connection: sqlite3.Connection, file_hash: str, source_path: str,
                   records: list[tuple[int, dict]], fingerprint: str = "") -> int:
    """追加 (row_number, record) 序列（record 内含 页码 键）。返回本次入库条数。

    页级替换语义（AE2）：同 row_number 已有旧行先删再插——失败页重跑覆盖旧内容、
    record 模式整文件覆盖、write_records 全新行号不受影响。页内序 seq 按入参顺序编 0..n-1。
    AP：写入时记下本次识别的 `fingerprint`，供下次判断缓存是否仍然有效。
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
                        json.dumps(record, ensure_ascii=False), fingerprint))
    cursor = connection.executemany(
        "INSERT INTO records(file_hash, source_path, row_number, seq, page_number, data, fingerprint) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
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
