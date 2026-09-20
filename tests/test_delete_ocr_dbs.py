"""AD1：删除任务连带清理 OCR 结果库。

- run 树任务输出里的 *.ocr_results.db / *.raw.json 随 purge_files=true 一并删除；
- 被树外 run 引用的共享库跳过并回报 dbs_shared；
- purge_ocr_dbs 只动 data 目录内、后缀匹配的文件。
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from services.pipeline_service import purge_ocr_dbs
from store.db import Db
from store.pipeline_repo import PipelineRepo
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def repo():
    db = Db(DB_URL)
    db.apply_migrations()
    yield PipelineRepo(db)


def _add_run(repo: PipelineRepo, flow: str = "flow.ocr.smart") -> str:
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, %s, %s, 'succeeded', now())",
            (rid, flow, __import__("psycopg.types.json", fromlist=["Json"]).Json({"file": "/u/a.pdf"})))
    return rid


def _add_task(repo: PipelineRepo, rid: str, output: dict) -> str:
    handle = "t_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status, output) "
            "VALUES (%s, 'img.vl.extract', '{}'::jsonb, 1, %s, 1, 'succeeded', %s)",
            (handle, rid, __import__("psycopg.types.json", fromlist=["Json"]).Json(output)))
    return handle


def _cleanup(repo: PipelineRepo, ids: list[str]) -> None:
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        for rid in ids:
            conn.execute("DELETE FROM tasks WHERE pipeline_run = %s", (rid,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))


def test_purges_db_and_raw_json(repo, tmp_path):
    data = tmp_path / "data"
    ocr = data / "ocr"
    ocr.mkdir(parents=True)
    db_file = ocr / "x.ocr_results.db"
    raw_file = ocr / "x.ocr_results.db.raw.json"
    db_file.write_bytes(b"db")
    raw_file.write_text("{}", encoding="utf-8")

    rid = _add_run(repo)
    _add_task(repo, rid, {"db": str(db_file), "raw_file": str(raw_file)})
    try:
        out = purge_ocr_dbs(repo, data, [rid])
        assert out["dbs_removed"] == 2 and out["dbs_shared"] == []
        assert not db_file.exists() and not raw_file.exists()
    finally:
        _cleanup(repo, [rid])


def test_shared_db_skipped(repo, tmp_path):
    data = tmp_path / "data"
    ocr = data / "ocr"
    ocr.mkdir(parents=True)
    db_file = ocr / "shared.ocr_results.db"
    db_file.write_bytes(b"db")

    rid_a, rid_b = _add_run(repo), _add_run(repo)
    _add_task(repo, rid_a, {"db": str(db_file)})
    _add_task(repo, rid_b, {"db": str(db_file)})  # 树外引用 → 共享
    try:
        out = purge_ocr_dbs(repo, data, [rid_a])
        assert out["dbs_removed"] == 0
        assert str(db_file) in out["dbs_shared"]
        assert db_file.exists()
    finally:
        _cleanup(repo, [rid_a, rid_b])


def test_outside_data_dir_untouched(repo, tmp_path):
    secret = tmp_path / "elsewhere.ocr_results.db"
    secret.write_bytes(b"keep")
    rid = _add_run(repo)
    _add_task(repo, rid, {"db": str(secret)})
    try:
        out = purge_ocr_dbs(repo, tmp_path / "data", [rid])  # data 目录不存在/不含该文件
        assert out["dbs_removed"] == 0 and secret.exists()
    finally:
        _cleanup(repo, [rid])
