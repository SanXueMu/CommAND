"""AF4：上传原件台账——来源记录 / 引用展示 / 单删与批量删 / 产物失效标记。"""
from __future__ import annotations

import json
import secrets
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from config import Config


@pytest.fixture
def client(tmp_path, monkeypatch):
    from api import files_router
    stub = Config(
        host="127.0.0.1", port=0, database_url="postgresql://x/x", worker_concurrency=1,
        heartbeat_interval_s=15, heartbeat_timeout_s=90,
        tools_dir=tmp_path, data_dir=tmp_path,
    )
    monkeypatch.setattr(deps, "get_config", lambda: stub)
    # 默认 stub 掉 PG 引用查询（fixture 无真库）；需要真库的用例自行覆盖
    monkeypatch.setattr(deps, "get_pipeline_repo",
                        lambda: type("R", (), {"runs_referencing_upload": staticmethod(
                            lambda name: [])})())
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c


def _ensure_flow(conn, flow_id: str) -> None:
    from psycopg.types.json import Json
    conn.execute(
        "INSERT INTO pipelines (id, name, steps) VALUES (%s, 'AF4', %s) "
        "ON CONFLICT (id) DO NOTHING",
        (flow_id, Json([{"tool": "tests.string.reverse", "input": {"text": "x"}}])))


def _upload_batch(client: TestClient, name: str, source: str = "ocr") -> dict:
    resp = client.post(f"/api/files/batch?source={source}",
                       files=[("files", (name, b"hello", "application/pdf"))])
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_records_source(client):
    """上传带 source → 清单落档 + 台账可见来源。"""
    out = _upload_batch(client, "a来源.pdf", source="translate")
    listing = client.get("/api/files/uploads").json()["uploads"]
    mine = next(u for u in listing if u["dir"] in out["path"])
    assert mine["source"] == "translate"
    assert mine["count"] == 1 and mine["size"] > 0
    assert mine["runs"]["count"] == 0  # 尚无任务引用


def test_uploads_index_reports_references(client, tmp_path, monkeypatch):
    """被任务引用的原件：引用数与最新状态可见；删除被 409 拦下。"""
    from store.pipeline_repo import PipelineRepo
    from store.db import Db
    from tests._dbutil import db_reachable
    if not db_reachable("postgresql://command_dev:root@192.168.8.41:5432/command_dev"):
        pytest.skip("dev PG 不可达")
    out = _upload_batch(client, "b引用.pdf")
    db = Db("postgresql://command_dev:root@192.168.8.41:5432/command_dev")
    repo = PipelineRepo(db)
    import deps as _deps
    real_repo = repo
    monkeypatch.setattr(_deps, "get_pipeline_repo", lambda: real_repo)
    rid = "p_" + secrets.token_hex(8)
    from psycopg.types.json import Json
    with db.pool.connection() as conn:
        _ensure_flow(conn, "flow.af4.test")
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af4.test', %s, 'succeeded', now())",
            (rid, Json({"file": out["files"][0]["path"]})))
    try:
        listing = client.get("/api/files/uploads").json()["uploads"]
        mine = next(u for u in listing if u["dir"] in out["path"])
        assert mine["runs"] == {"count": 1, "latest_status": "succeeded"}
        resp = client.request("DELETE", "/api/files/uploads",
                              json={"roots": [Path(out["path"]).name]})
        assert resp.status_code == 409
        assert "仍被 1 个任务引用" in resp.json()["detail"]
    finally:
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))
        db.close()


def test_delete_unreferenced_uploads(client, tmp_path):
    """无引用原件可删（含批量）；目录与批次清单一并清理。"""
    a = _upload_batch(client, "c可删1.pdf")
    b = _upload_batch(client, "d可删2.pdf")
    roots = [Path(a["path"]).name, Path(b["path"]).name]
    resp = client.request("DELETE", "/api/files/uploads", json={"roots": roots})
    assert resp.status_code == 200
    assert sorted(resp.json()["removed"]) == sorted(roots)
    assert not Path(a["path"]).exists() and not Path(b["path"]).exists()
    listing = client.get("/api/files/uploads").json()["uploads"]
    assert not any(u["dir"] in roots for u in listing)


def test_uploads_files_lists_details(client, tmp_path):
    """AN：某批次目录的文件明细（相对 rel 保留结构 + 绝对 path 可直接起 run）。"""
    day = tmp_path / "uploads" / date.today().isoformat() / "abcd1234_合同目录"
    (day / "子目录").mkdir(parents=True)
    (day / "a.pdf").write_bytes(b"x")
    (day / "子目录" / "b.docx").write_bytes(b"yy")
    (day / ".DS_Store").write_bytes(b"junk")  # 系统垃圾应过滤
    out = client.get("/api/files/uploads/files", params={"dir": "abcd1234_合同目录"})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["count"] == 2
    rels = sorted(f["rel"] for f in body["files"])
    assert rels == ["a.pdf", "子目录/b.docx"]
    assert all(Path(f["path"]).is_file() and f["size"] > 0 for f in body["files"])


def test_uploads_files_rejects_injection(client):
    """AN：只接受目录名——上跳/绝对路径/多段路径一律 422。"""
    for bad in ["../x", "/etc", "a/b", ""]:
        resp = client.get("/api/files/uploads/files", params={"dir": bad})
        assert resp.status_code == 422, f"{bad!r} 应被拒: {resp.text}"


def test_uploads_files_unknown_dir(client):
    assert client.get("/api/files/uploads/files",
                      params={"dir": "不存在目录"}).status_code == 404


def test_missing_artifacts_flag(client, monkeypatch):
    """run 详情：产物文件已不在盘 → missing_artifacts 列出（前端标「已删除」）。"""
    from store.pipeline_repo import PipelineRepo
    from store.db import Db
    from tests._dbutil import db_reachable
    if not db_reachable("postgresql://command_dev:root@192.168.8.41:5432/command_dev"):
        pytest.skip("dev PG 不可达")
    out = _upload_batch(client, "e产物.pdf")
    db = Db("postgresql://command_dev:root@192.168.8.41:5432/command_dev")
    repo = PipelineRepo(db)
    rid = "p_" + secrets.token_hex(8)
    gone = str(Path(out["path"]).parent / "已删.ocr_results.db")
    from psycopg.types.json import Json
    with db.pool.connection() as conn:
        _ensure_flow(conn, "flow.af4.test")
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af4.test', %s, 'succeeded', now())",
            (rid, Json({"file": out["files"][0]["path"]})))
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status, output) "
            "VALUES (%s, 'tests.string.reverse', '{}'::jsonb, 1, %s, 0, 'succeeded', %s)",
            ("t_" + secrets.token_hex(8), rid, Json({"db": gone})))
    try:
        from api import pipelines_router as pr
        monkeypatch.setattr(pr.deps, "get_pipeline_service",
                            lambda: type("S", (), {"get_run_tasks": staticmethod(
                                lambda r: [{"output": {"db": gone}}]),
                                "detail_summary": staticmethod(lambda r: None)})())
        monkeypatch.setattr(pr.deps, "get_pipeline_repo",
                            lambda: type("R", (), {"get_run": staticmethod(lambda r: {"id": r})})())
        detail = pr.get_pipeline_run(rid)
        assert detail["missing_artifacts"] == [gone]
    finally:
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM tasks WHERE pipeline_run = %s", (rid,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = %s", (rid,))
        db.close()
