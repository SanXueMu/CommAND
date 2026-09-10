"""协议 v2 站点清单（蓝图 03）：/meta/site 端点与声明结构完整性。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.meta_router import SITE_MANIFEST, router as meta_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(meta_router, prefix="/api")
    return TestClient(app)


def test_site_manifest_shape() -> None:
    site = SITE_MANIFEST["site"]
    assert site["name"]
    assert site["protocolVersion"] == "2"
    ids = [v["id"] for v in site["views"]]
    assert len(ids) == len(set(ids)), "视图 id 不得重复"
    assert sum(1 for v in site["views"] if v.get("default")) <= 1, "default 视图至多一个"
    for view in site["views"]:
        assert view["id"] and view["type"] and view["title"]
        if "when" in view:
            assert set(view["when"]) == {"capability"}, "when 仅支持 capability 条件"


def test_site_endpoint(client: TestClient) -> None:
    resp = client.get("/api/meta/site")
    assert resp.status_code == 200
    body = resp.json()["site"]
    assert body["protocolVersion"] == "2"
    types = {v["type"] for v in body["views"]}
    assert {"tools.grid", "flows.list", "tasks.table", "workspace.tabs"} <= types
