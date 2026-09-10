"""协议 v2 站点清单（蓝图 03）：内置声明结构与 /meta/site 端点一致性（PG 装配版）。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from store.site_seed import BUILTIN_SITE_VIEWS


def test_builtin_site_views_shape() -> None:
    ids = [v["id"] for v in BUILTIN_SITE_VIEWS]
    assert len(ids) == len(set(ids)), "视图 id 不得重复"
    assert sum(1 for v in BUILTIN_SITE_VIEWS if v.get("default")) <= 1, "default 视图至多一个"
    for view in BUILTIN_SITE_VIEWS:
        assert view["id"] and view["type"] and view["title"]
        if "when" in view:
            assert set(view["when"]) == {"capability"}, "when 仅支持 capability 条件"


def test_builtin_includes_protocol_and_ocr_views() -> None:
    ids = set(ids for ids in (v["id"] for v in BUILTIN_SITE_VIEWS))
    assert {"tools", "flows", "tasks", "work", "settings"} <= ids, "协议级通用视图必须在内置声明中"
    assert {"ocr-recognize", "ocr-results", "ocr-views", "ocr-specgen"} <= ids, "OCR 业务声明必须在内置声明中"


def test_meta_site_serves_from_repo(monkeypatch) -> None:
    """端点从 repo 装配：假 repo 返回 seed 声明 → /meta/site 原样下发。"""

    class FakeRepo:
        def list(self):
            return [
                {
                    "id": "tools", "type": "tools.grid", "title": "工具库", "icon": "appstore-outlined",
                    "when": None, "props": {"defaultLayout": "card"}, "sort": 10, "default": True,
                },
                {
                    "id": "ocr-views", "type": "data.browser", "title": "OCR 视图导出", "icon": None,
                    "when": {"capability": "has_files"}, "props": {"source": {"kind": "records_json"}}, "sort": 120, "default": False,
                },
            ]

    import deps
    from api import meta_router

    monkeypatch.setattr(deps, "get_site_repo", lambda: FakeRepo())
    app = FastAPI()
    app.include_router(meta_router.router, prefix="/api")
    client = TestClient(app)
    body = client.get("/api/meta/site").json()["site"]
    assert body["protocolVersion"] == "2"
    assert [v["id"] for v in body["views"]] == ["tools", "ocr-views"]
    assert "when" not in body["views"][0], "when 为 None 时不得下发空键"
    assert body["views"][1]["when"] == {"capability": "has_files"}
