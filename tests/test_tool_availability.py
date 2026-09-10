"""06 D1 工具启停/显隐：PATCH availability 端点 + repo 行为（真库，不可达自动跳过）。"""

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from store.db import Db
from store.tool_repo import ToolRepo

VALID_TOOL_TOML = """
[tool]
id = "{tool_id}"
name = "可用性测试"
version = "1.0.0"
description = "06 D1 测试工具"

[io]
input_schema = "input.schema.json"
output_schema = "output.schema.json"
input_types = []
output_types = []

[runtime]
kind = "inproc"
entry = "main.py:run"

[resources]
timeout_s = 60
concurrency = 1
max_attempts = 1
"""

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")
TEST_TOOL = "test.availability.echo"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev 库不可达")


@pytest.fixture
def avail_client(monkeypatch, tmp_path):
    """最小 app：只挂 tools 路由；测试后还原工具状态。"""
    from api import tools_router
    from core.protocol import ToolManifest

    db = Db(DB_URL)
    repo = ToolRepo(db)
    # 自注册独立测试工具（tmp_path，不污染真实落位区；teardown 删行）
    tool_dir = tmp_path / "test" / "availability_echo"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.toml").write_text(
        VALID_TOOL_TOML.format(tool_id=TEST_TOOL), encoding="utf-8"
    )
    (tool_dir / "input.schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (tool_dir / "output.schema.json").write_text('{"type":"object"}', encoding="utf-8")
    repo.upsert(ToolManifest.from_toml(tool_dir / "tool.toml"), path=str(tool_dir))
    monkeypatch.setattr(deps, "get_tool_repo", lambda: repo)
    app = FastAPI()
    app.include_router(tools_router.router)
    with TestClient(app) as c:
        yield c, repo
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tools WHERE id = %s", (TEST_TOOL,))


def test_patch_availability_roundtrip(avail_client):
    client, repo = avail_client
    r = client.patch(f"/tools/{TEST_TOOL}/availability", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    # 语义（06 D1）：disabled=列表仍返回但 enabled=false（前端置灰可管理）；hidden=不返回
    listing = {t["id"]: t for t in client.get("/tools").json()["tools"]}
    assert listing[TEST_TOOL]["enabled"] is False
    ids = [t["id"] for t in client.get("/tools").json()["tools"] if not t["hidden"]]
    assert TEST_TOOL in ids
    # repo 层 get 默认只认 active（发现语义），include_disabled 供注册校验/管理面
    assert repo.get(TEST_TOOL) is None
    assert repo.get(TEST_TOOL, include_disabled=True)["enabled"] is False
    # hidden=true → 列表不可见（即使 enabled）
    r = client.patch(f"/tools/{TEST_TOOL}/availability", json={"enabled": True, "hidden": True})
    assert r.json()["hidden"] is True and r.json()["enabled"] is True
    ids = [t["id"] for t in client.get("/tools").json()["tools"]]
    assert TEST_TOOL not in ids
    # include_hidden 视角可见（管理面）
    all_tools = repo.list_active(include_hidden=True)
    assert any(t["id"] == TEST_TOOL and t["enabled"] for t in all_tools)


def test_patch_availability_validation(avail_client):
    client, _ = avail_client
    # 空体 422
    assert client.patch(f"/tools/{TEST_TOOL}/availability", json={}).status_code == 422
    # 不存在 404
    assert client.patch("/tools/no.such.tool/availability", json={"enabled": False}).status_code == 404
