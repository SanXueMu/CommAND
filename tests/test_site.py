"""site_views 集成测试：seed 幂等 + /meta/site PG 装配（真库不可达自动跳过）。"""

import os

import pytest
from fastapi.testclient import TestClient

import deps
from config import Config
from store.db import Db
from store.site_repo import SiteRepo
from store.site_seed import BUILTIN_SITE_VIEWS

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev 库不可达")


@pytest.fixture
def site_stack():
    db = Db(DB_URL)
    db.apply_migrations()
    return SiteRepo(db)


def test_seed_is_idempotent(site_stack):
    repo = site_stack
    repo.seed(BUILTIN_SITE_VIEWS)
    first = {v["id"] for v in repo.list()}
    repo.seed(BUILTIN_SITE_VIEWS)
    second = {v["id"] for v in repo.list()}
    assert first == second
    assert "ocr-recognize" in first
    assert "tools" in first


def test_upsert_overrides_and_delete(site_stack):
    repo = site_stack
    repo.upsert({"id": "test-view", "type": "data.browser", "title": "测试", "sort": 999})
    assert any(v["id"] == "test-view" for v in repo.list())
    assert repo.delete("test-view")
    assert not any(v["id"] == "test-view" for v in repo.list())


def test_meta_site_serves_seeded_views(site_stack, monkeypatch):
    repo = site_stack
    repo.seed(BUILTIN_SITE_VIEWS)
    monkeypatch.setattr(deps, "get_site_repo", lambda: repo)

    from fastapi import FastAPI

    from api import meta_router

    app = FastAPI()
    app.include_router(meta_router.router, prefix="/api")
    client = TestClient(app)
    body = client.get("/api/meta/site").json()
    views = body["site"]["views"]
    ids = [v["id"] for v in views]
    assert "tools" in ids and "ocr-specgen" in ids
    # when 条件下发形态与 props 保留
    specgen = next(v for v in views if v["id"] == "ocr-specgen")
    assert specgen["props"]["save_as"]["pipeline_prefix"] == "flow.ocr.custom."
    assert specgen["when"] == {"capability": "has_files"}
