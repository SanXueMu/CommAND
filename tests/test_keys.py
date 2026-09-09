"""keys 服务集成测试：真库（不可达自动跳过）+ ctx 注入端到端。"""

import os

import pytest
from fastapi.testclient import TestClient

import deps
from config import Config
from core.runner import Runner
from core.scheduler import Scheduler
from store.db import Db
from store.event_repo import EventRepo
from store.key_repo import KeyRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")
TEST_KEY = "test.translate.key"
TEST_TOOL_ID = "test.keys.echo"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


@pytest.fixture
def key_client(monkeypatch):
    """最小 app：只挂 keys 路由，绕开 lifespan/scheduler；仓储直连 41 dev 库。"""
    from fastapi import FastAPI

    from api import keys_router

    db = Db(DB_URL)
    db.apply_migrations()
    repo = KeyRepo(db)
    monkeypatch.setattr(deps, "get_key_repo", lambda: repo)
    app = FastAPI()
    app.include_router(keys_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, repo
    db.close()


def _cleanup(repo: KeyRepo) -> None:
    repo.delete(TEST_KEY)


@pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")
class TestKeyRepo:
    def test_upsert_list_masked_and_default_single(self):
        db = Db(DB_URL)
        db.apply_migrations()
        repo = KeyRepo(db)
        try:
            repo.upsert(TEST_KEY, "dashscope", "https://example.com/v1", "sk-abcdef123456", is_default=False)
            repo.upsert(TEST_KEY + "_d", "dashscope", "", "sk-0000zzzz9999", is_default=True)
            repo.upsert(TEST_KEY, "dashscope", "https://example.com/v1", "sk-abcdef123456", is_default=True)

            keys = {k["name"]: k for k in repo.list()}
            assert keys[TEST_KEY]["api_key"] == "****3456", "列表必须打码"
            assert keys[TEST_KEY + "_d"]["is_default"] is False, "设新默认应取消旧默认"
            assert keys[TEST_KEY]["is_default"] is True

            runtime = repo.all_for_runtime()
            assert runtime[TEST_KEY]["api_key"] == "sk-abcdef123456", "运行时注入为明文"
        finally:
            _cleanup(repo)
            repo.delete(TEST_KEY + "_d")
            db.close()

    def test_delete(self):
        db = Db(DB_URL)
        db.apply_migrations()
        repo = KeyRepo(db)
        try:
            repo.upsert(TEST_KEY, "dashscope", "", "sk-x", is_default=False)
            assert repo.delete(TEST_KEY) is True
            assert repo.delete(TEST_KEY) is False
        finally:
            _cleanup(repo)
            db.close()


@pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")
class TestKeysRouter:
    def test_put_get_delete_roundtrip(self, key_client):
        client, repo = key_client
        try:
            resp = client.put(
                f"/api/keys/{TEST_KEY}",
                json={"name": TEST_KEY, "provider": "dashscope", "base_url": "https://x/v1", "api_key": "sk-router1234", "is_default": False},
            )
            assert resp.status_code == 200
            resp = client.get("/api/keys")
            entry = next(k for k in resp.json()["keys"] if k["name"] == TEST_KEY)
            assert entry["api_key"] == "****1234"
            resp = client.delete(f"/api/keys/{TEST_KEY}")
            assert resp.status_code == 200
            assert client.delete(f"/api/keys/{TEST_KEY}").status_code == 404
        finally:
            _cleanup(repo)


@pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")
class TestKeysInjectionE2E:
    def test_inproc_tool_receives_keys_via_ctx(self, tmp_path):
        db = Db(DB_URL)
        db.apply_migrations()
        key_repo = KeyRepo(db)
        tool_repo = ToolRepo(db)
        task_repo = TaskRepo(db)
        key_repo.upsert(TEST_KEY, "dashscope", "https://x/v1", "sk-e2e9999", is_default=False)

        tool_dir = tmp_path / "echo"
        tool_dir.mkdir()
        (tool_dir / "main.py").write_text(
            "def run(input, ctx, emit):\n"
            "    return {'got': ctx.keys.get('test.translate.key', {}).get('api_key', '')}\n",
            encoding="utf-8",
        )
        from core.protocol import ToolManifest

        manifest = ToolManifest.model_validate({
            "tool": {"id": TEST_TOOL_ID, "name": "t", "version": "1.0.0"},
            "io": {
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "input_types": ["text.raw[]"],
                "output_types": ["text.translated[]"],
            },
            "runtime": {"kind": "inproc", "entry": "main.py:run"},
            "resources": {"timeout_s": 30, "concurrency": 1, "max_attempts": 1},
        })
        tool_repo.upsert(manifest, path=str(tool_dir))
        try:
            sched = Scheduler(
                db=db, runner=Runner(), task_repo=task_repo, tool_repo=tool_repo,
                event_repo=EventRepo(db), key_repo=key_repo,
                config=Config(
                    host="127.0.0.1", port=0, database_url=DB_URL, worker_concurrency=1,
                    heartbeat_interval_s=15, heartbeat_timeout_s=90,
                    tools_dir=tmp_path, data_dir=tmp_path,
                ),
            )
            handle = task_repo.enqueue(TEST_TOOL_ID, {}, max_attempts=1)
            assert sched.run_once("w-test") is True
            task = task_repo.get(handle)
            assert task["status"] == "succeeded"
            assert task["output"] == {"got": "sk-e2e9999"}, "ctx.keys 应注入运行时密钥"
        finally:
            with db.pool.connection() as conn:
                conn.execute("DELETE FROM tasks WHERE tool_id = %s", (TEST_TOOL_ID,))
                conn.execute("DELETE FROM tools WHERE id = %s", (TEST_TOOL_ID,))
            key_repo.delete(TEST_KEY)
            db.close()
