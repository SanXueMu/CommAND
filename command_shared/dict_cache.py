"""SQLite 字典缓存（translate 内部机制，对管线不可见）：归一文本哈希 → 译文。

字典全局共用（跨文件/跨任务）：key = sha256(归一文本)，同一文本一生只翻一次。
status: ok=合格 / review=质检未过待人工。缓存库位置：COMMAND_DATA_DIR/dict_cache.db。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

# 批量并发写同一 SQLite 时的等待/重试参数（2026-09-14 线上「database is locked」修复）：
# ① timeout=30：连接级锁等待；② WAL：读写不互斥；③ busy_timeout：SQLite 自身重试；
# ④ 外层再包一层退避重试，兜住 WAL checkpoint 等瞬时锁。
_DB_TIMEOUT_S = 30.0
_BUSY_TIMEOUT_MS = 30_000
_WRITE_RETRIES = 3

# 进程内互斥：所有任务都跑在同一个进程的线程里（scheduler worker），
# 每任务各开一条连接 → 单靠 SQLite 的 busy 等待会互相排队甚至瞬时失败；
# 这里先把进程内访问串行化，跨进程才交给 busy_timeout/重试。
_DB_LOCK = threading.RLock()

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
    # check_same_thread=False：同一连接可能被引擎的 checkpoint 回调跨线程使用；
    # 安全性由 _DB_LOCK 串行化保证。
    with _DB_LOCK:
        conn = sqlite3.connect(db_path or default_db_path(), timeout=_DB_TIMEOUT_S,
                               check_same_thread=False)
        # WAL：多读单写并发下不互斥（批量任务 + 引擎多线程会同时写字典）
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:  # noqa: BLE001 —— 只读挂载等场景退化为默认日志模式
            pass
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        conn.executescript(_SCHEMA)
    return conn


def with_lock_retry(fn, *args, **kwargs):
    """在写锁竞争时退避重试（SQLite 的 database is locked 是瞬时状态，不该让整个任务失败）。"""
    delay = 0.2
    for attempt in range(_WRITE_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or attempt >= _WRITE_RETRIES:
                raise
            time.sleep(delay)
            delay *= 2


def text_key(norm_text: str) -> str:
    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()


def lookup(conn: sqlite3.Connection, keys: list[str]) -> dict[str, dict]:
    """批量查缓存 → {key: {source, translated, model, status}}。"""
    result: dict[str, dict] = {}
    with _DB_LOCK:
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
    def _write() -> None:
        conn.execute(
            "INSERT INTO translations (key, source, translated, model, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET translated=excluded.translated, "
            "model=excluded.model, status=excluded.status",
            (key, source, translated, model, status, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()

    with _DB_LOCK:
        with_lock_retry(_write)


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
