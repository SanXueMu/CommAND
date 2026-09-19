"""X5 用户视图库单测：存取/校验/内置保护/同名覆盖/REST CRUD（tmp 目录，不碰真实 data/）。"""

import os

import pytest
from fastapi.testclient import TestClient

from store.ocr_view_store import ViewStore
from core.errors import ToolDomainError, ToolNotFoundError


@pytest.fixture
def store(tmp_path):
    return ViewStore(str(tmp_path))


def _valid(vid="view.demo", name="我的凭证视图", **kw):
    return {"id": vid, "name": name, "spec": {"type": "records", "limit": 50}, **kw}


def test_upsert_create_update_roundtrip(store):
    assert store.upsert(_valid())["status"] == "created"
    item = store.get("view.demo")
    assert item["name"] == "我的凭证视图" and item["spec"]["type"] == "records"
    assert item["created_at"] == item["updated_at"]

    store.upsert(_valid(name="改名"))
    item = store.get("view.demo")
    assert item["name"] == "改名"
    assert item["created_at"] <= item["updated_at"]  # 创建时间保留


def test_upsert_validation(store):
    with pytest.raises(ToolDomainError, match="id"):
        store.upsert(_valid(vid="X"))
    with pytest.raises(ToolDomainError, match="内置"):
        store.upsert(_valid(vid="builtin.records"))  # 内置 id 前缀保留
    with pytest.raises(ToolDomainError, match="name"):
        store.upsert(_valid(name="  "))
    with pytest.raises(ToolDomainError, match="spec"):
        store.upsert(_valid(spec={"no_type": 1}))
    with pytest.raises(ToolDomainError, match="spec"):
        store.upsert(_valid(spec=[]))


def test_delete_and_missing(store):
    store.upsert(_valid())
    assert store.delete("view.demo")["status"] == "deleted"
    with pytest.raises(ToolNotFoundError):
        store.get("view.demo")


@pytest.fixture
def client(tmp_path):
    from fastapi import FastAPI
    from api import ocr_view_router

    app = FastAPI()
    app.include_router(ocr_view_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path


def test_rest_crud(client):
    c, tmp_path = client
    import api.ocr_view_router as vr
    vr.ViewStore = lambda data_dir=None: ViewStore(str(tmp_path))

    r = c.post("/api/ocr/views", json={"name": "我的凭证视图", "spec": {"type": "records"}})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    assert vid.startswith("view.")

    r = c.get("/api/ocr/views")
    assert [v["id"] for v in r.json()["views"]] == [vid]

    # 同名覆盖 → updated，created_at 保留
    r = c.post("/api/ocr/views", json={"id": vid, "name": "改名", "spec": {"type": "pivot"}})
    assert r.json()["status"] == "updated"
    got = c.get(f"/api/ocr/views/{vid}").json()
    assert got["spec"]["type"] == "pivot" and got["name"] == "改名"

    # 内置保护走 422
    r = c.post("/api/ocr/views", json={"id": "builtin.x", "name": "x", "spec": {"type": "records"}})
    assert r.status_code == 422

    assert c.delete(f"/api/ocr/views/{vid}").json()["status"] == "deleted"
    assert c.get("/api/ocr/views").json()["views"] == []
