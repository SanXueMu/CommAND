"""SQLite 字典缓存（translate 内部机制，对管线不可见）：归一文本哈希 → 译文。

字典全局共用（跨文件/跨任务）：key = sha256(归一文本)，同一文本一生只翻一次。
status: ok=合格 / review=质检未过待人工。缓存库位置：COMMAND_DATA_DIR/dict_cache.db。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    translated  TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'ok',
    created_at  TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "dict_cache.db"


def open_dict(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or default_db_path())
    conn.executescript(_SCHEMA)
    return conn


def text_key(norm_text: str) -> str:
    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()


def lookup(conn: sqlite3.Connection, keys: list[str]) -> dict[str, dict]:
    """批量查缓存 → {key: {source, translated, model, status}}。"""
    result: dict[str, dict] = {}
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT key, source, translated, model, status FROM translations "
            f"WHERE key IN ({placeholders})",
            chunk,
        ).fetchall()
        for key, source, translated, model, status in rows:
            result[key] = {"source": source, "translated": translated, "model": model, "status": status}
    return result


def save(
    conn: sqlite3.Connection,
    key: str,
    source: str,
    translated: str,
    model: str = "",
    status: str = "ok",
) -> None:
    conn.execute(
        "INSERT INTO translations (key, source, translated, model, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET translated=excluded.translated, "
        "model=excluded.model, status=excluded.status",
        (key, source, translated, model, status, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    """字典概览：总数 + 按状态分布（ok=合格 / review=待审）。"""
    rows = conn.execute("SELECT status, count(*) FROM translations GROUP BY status").fetchall()
    by_status = {status: int(count) for status, count in rows}
    return {"total": sum(by_status.values()), "ok": by_status.get("ok", 0),
            "review": by_status.get("review", 0), "by_status": by_status}


def browse(
    conn: sqlite3.Connection,
    q: str | None = None,
    status: str | None = None,
    model: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """字典浏览（translee「已译字典」体验）：原文/译文模糊检索 + 状态/模型筛选 + 分页。"""
    where: list[str] = []
    params: list = []
    if q:
        where.append("(source LIKE ? OR translated LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if status:
        where.append("status = ?")
        params.append(status)
    if model:
        where.append("model = ?")
        params.append(model)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT count(*) FROM translations{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT source, translated, model, status, created_at FROM translations{clause} "
        f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    models = [r[0] for r in conn.execute(
        "SELECT DISTINCT model FROM translations WHERE model != '' ORDER BY model").fetchall()]
    return {
        "rows": [{"source": s, "translated": t, "model": m, "status": st, "created_at": c}
                 for s, t, m, st, c in rows],
        "total": int(total), "limit": limit, "offset": offset,
        "stats": stats(conn), "models": models,
    }
