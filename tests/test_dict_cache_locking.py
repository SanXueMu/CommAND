"""字典缓存并发写（SQLite）——2026-09-14 线上 `OperationalError: database is locked` 回归。

批量任务下多条 llm.translate 并行（工具级并发闸 = 2）各自持连接写同一个 dict_cache.db，
裸 sqlite3.connect 无 WAL / 无 busy_timeout 时必然锁冲突，整条 xlsx 任务失败。
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from command_shared import dict_cache


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    return tmp_path / "dict_cache.db"


def test_open_dict_enables_wal_and_busy_timeout(db_path):
    conn = dict_cache.open_dict(db_path)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) == dict_cache._BUSY_TIMEOUT_MS
    finally:
        conn.close()


def test_with_lock_retry_retries_transient_lock():
    """瞬时 database is locked 应退避重试而不是直接把任务判死。"""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    assert dict_cache.with_lock_retry(flaky) == "ok"
    assert calls["n"] == 3


def test_with_lock_retry_does_not_swallow_other_errors():
    def boom():
        raise sqlite3.OperationalError("no such table: translations")

    with pytest.raises(sqlite3.OperationalError):
        dict_cache.with_lock_retry(boom)


def test_concurrent_writes_from_two_connections_do_not_lock(db_path):
    """两条连接（= 两个并行任务，各自线程内建连）交替写同一库：全部成功、无 database is locked。"""
    errors: list[Exception] = []

    def writer(tag: str) -> None:
        try:
            conn = dict_cache.open_dict(db_path)  # 每个任务在自己的线程里建连（与工具实现一致）
            try:
                for i in range(60):
                    key = dict_cache.text_key(f"{tag}-{i}")
                    dict_cache.save(conn, key, f"{tag}-{i}", f"{tag}译文{i}", "qwen-mt-flash")
            finally:
                conn.close()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=writer, args=("a",)),
               threading.Thread(target=writer, args=("b",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [], errors

    conn = dict_cache.open_dict(db_path)
    assert conn.execute("SELECT count(*) FROM translations").fetchone()[0] == 120
    conn.close()
