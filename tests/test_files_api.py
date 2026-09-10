"""files 路由测试：纯文件系统，零外部依赖。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import deps
from config import Config


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """data_dir 指向 tmp_path；最小 app 只挂 files 路由，零 DB 依赖。"""
    from fastapi import FastAPI

    from api import data_router, files_router

    stub = Config(
        host="127.0.0.1", port=0, database_url="postgresql://x/x", worker_concurrency=1,
        heartbeat_interval_s=15, heartbeat_timeout_s=90,
        tools_dir=tmp_path, data_dir=tmp_path,
    )
    monkeypatch.setattr(deps, "get_config", lambda: stub)
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    app.include_router(data_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path


def test_upload_saves_and_returns_path(client):
    c, tmp_path = client
    resp = c.post(
        "/api/files",
        files={"file": ("报表.xlsx", b"PK\x03\x04 fake-xlsx-bytes", "application/octet-stream")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "报表.xlsx"
    assert body["size"] > 0
    saved = Path(body["path"])
    assert saved.exists() and saved.read_bytes().startswith(b"PK")
    assert tmp_path in saved.parents, "必须落在 data_dir 内"


def test_upload_empty_rejected(client):
    c, _ = client
    resp = c.post("/api/files", files={"file": ("empty.txt", b"", "text/plain")})
    assert resp.status_code == 422


def test_download_within_data_dir(client):
    c, tmp_path = client
    target = tmp_path / "outputs" / "导出.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"PK\x03\x04 download-me")
    resp = c.get("/api/files/download", params={"path": str(target)})
    assert resp.status_code == 200
    assert resp.content == b"PK\x03\x04 download-me"
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_download_blocks_traversal_and_missing(client):
    c, tmp_path = client
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("no")
    resp = c.get("/api/files/download", params={"path": str(outside)})
    assert resp.status_code == 403
    resp = c.get("/api/files/download", params={"path": str(tmp_path / "nope.xlsx")})
    assert resp.status_code == 404


def test_list_dbs(client):
    c, tmp_path = client
    db1 = tmp_path / "ocr" / "决算.ocrdb"
    db1.parent.mkdir(parents=True, exist_ok=True)
    db1.write_bytes(b"SQLite format 3")
    resp = c.get("/api/data/dbs")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["dbs"]]
    assert names == ["决算.ocrdb"]
    assert resp.json()["dbs"][0]["size"] > 0
