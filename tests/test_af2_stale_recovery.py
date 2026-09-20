"""AF2：启动 stale 收口——进程重启后残留 running run → interrupted（可重跑）。"""
from __future__ import annotations

import secrets

import pytest

from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo, ToolManifest
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def stack(tmp_path):
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    tool_repo.upsert(ToolManifest.from_toml(
        __import__("pathlib").Path(__file__).parents[1] / "tests" / "fixtures" / "string_reverse" / "tool.toml"),
        path="tests/fixtures/string_reverse")
    pipeline_repo = PipelineRepo(db)
    run_event_repo = RunEventRepo(db)
    svc = PipelineService(
        db=db, pipeline_repo=pipeline_repo, task_repo=TaskRepo(db),
        tool_repo=tool_repo,
        dispatch_service=__import__("services.dispatch_service", fromlist=["DispatchService"]).DispatchService(
            db=db, task_repo=TaskRepo(db), tool_repo=tool_repo, event_repo=EventRepo(db)),
        run_event_repo=run_event_repo, data_dir=tmp_path)
    svc.register("flow.af2.test", "AF2 测试流",
                 [{"tool": "tests.string.reverse", "input": {"text": "x"}}])
    yield {"svc": svc, "repo": pipeline_repo, "audit": run_event_repo}
    db.close()


def _insert_run(repo: PipelineRepo, status: str) -> str:
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        from psycopg.types.json import Json
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af2.test', %s, %s, now())",
            (rid, Json({"file": "/tmp/af2.pdf"}), status))
    return rid


def test_stale_running_recovered(stack):
    """running → interrupted（错误注明进程重启、事件留痕、可重跑语义）。"""
    repo, svc = stack["repo"], stack["svc"]
    stale = _insert_run(repo, "running")
    paused = _insert_run(repo, "paused")  # 可继续语义：不动
    try:
        recovered = svc.recover_stale_runs()
        assert stale in recovered and paused not in recovered
        run = repo.get_run(stale)
        assert run["status"] == "interrupted"
        assert "进程重启" in str(run["error"])
        events = stack["audit"].list(stale)
        assert any(e["kind"] == "run_recovered" for e in events)
    finally:
        for rid in (stale, paused):
            repo.delete_run(rid, drop_tasks=True)


def test_rerunnable_includes_interrupted(stack):
    """interrupted 属可重跑状态（重跑入口继续可用）。"""
    repo, svc = stack["repo"], stack["svc"]
    rid = _insert_run(repo, "interrupted")
    try:
        files = svc.rerunnable_runs()["files"]
        assert any(f["file"] == "/tmp/af2.pdf" for f in files)
    finally:
        repo.delete_run(rid, drop_tasks=True)


def test_recover_idempotent(stack):
    """重复调用无残留时不报错、返回空。"""
    repo, svc = stack["repo"], stack["svc"]
    assert svc.recover_stale_runs() == []
