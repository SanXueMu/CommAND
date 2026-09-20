"""AD3：结果库面板删除端点 DELETE /api/data/dbs。

- 数据目录外 / 非 .ocr_results.db → 拒绝；
- 被成功任务引用 → 409 冲突回报引用数；
- 无引用 → 删库 + .raw.json 留痕一并清。
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from api import data_router
from store.db import Db
from store.pipeline_repo import PipelineRepo
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


class _Cfg:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = str(data_dir)


@pytest.fixture
def app(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "ocr").mkdir(parents=True)
    monkeypatch.setattr(deps, "get_config", lambda: _Cfg(data))
    monkeypatch.setattr(deps, "get_db", lambda: Db(DB_URL))
    application = FastAPI()
    application.include_router(data_router.router, prefix="/api")
    return application, data


def _referencing_run(repo: PipelineRepo, db_path: str) -> str:
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.ocr.smart', '{}'::jsonb, 'succeeded', now())", (rid,))
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status, output) "
            "VALUES (%s, 'img.vl.extract', '{}'::jsonb, 1, %s, 1, 'succeeded', %s)",
            ("t_" + secrets.token_hex(8), rid,
             __import__("psycopg.types.json", fromlist=["Json"]).Json({"db": db_path})))
    return rid


def _cleanup(repo: PipelineRepo, rid: str) -> None:
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute("DELETE FROM tasks WHERE pipeline_run = %s", (rid,))
        conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))


def test_delete_db_and_raw(app):
    application, data = app
    db_file = data / "ocr" / "x.ocr_results.db"
    db_file.write_bytes(b"db")
    raw = data / "ocr" / "x.ocr_results.db.raw.json"
    raw.write_text("{}", encoding="utf-8")
    with TestClient(application) as c:
        resp = c.delete("/api/data/dbs", params={"path": str(db_file)})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["removed"]) == 2
    assert not db_file.exists() and not raw.exists()


def test_referenced_db_conflicts(app):
    application, data = app
    db_file = data / "ocr" / "y.ocr_results.db"
    db_file.write_bytes(b"db")
    repo = PipelineRepo(Db(DB_URL))
    rid = _referencing_run(repo, str(db_file))
    try:
        with TestClient(application) as c:
            resp = c.delete("/api/data/dbs", params={"path": str(db_file)})
        assert resp.status_code == 409
        assert "1 个任务引用" in resp.json()["detail"]
        assert db_file.exists()
    finally:
        _cleanup(repo, rid)


def test_outside_or_wrong_suffix_rejected(app):
    application, data = app
    with TestClient(application) as c:
        assert c.delete("/api/data/dbs", params={"path": "/etc/passwd"}).status_code == 400
        rogue = data / "rogue.txt"
        rogue.write_text("x")
        assert c.delete("/api/data/dbs", params={"path": str(rogue)}).status_code == 400


def test_force_delete_ignores_references(app):
    """AP-D：force=true 无视引用强删（引用它的任务详情会显示产物「已删除」）。"""
    application, data = app
    db_file = data / "ocr" / "z.ocr_results.db"
    db_file.write_bytes(b"db")
    raw = data / "ocr" / "z.ocr_results.db.raw.json"
    raw.write_text("{}", encoding="utf-8")
    repo = PipelineRepo(Db(DB_URL))
    rid = _referencing_run(repo, str(db_file))
    try:
        with TestClient(application) as c:
            blocked = c.delete("/api/data/dbs", params={"path": str(db_file)})
            assert blocked.status_code == 409
            resp = c.delete("/api/data/dbs", params={"path": str(db_file), "force": "true"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["forced"] is True and resp.json()["references"] == 1
        assert not db_file.exists() and not raw.exists()
    finally:
        _cleanup(repo, rid)
