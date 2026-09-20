"""AF1：删除任务彻底化——tasks 整删 + 同文件失败尝试连带清理 + 孤儿引用不算数。"""
from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from pathlib import Path
from store.tool_repo import ToolRepo
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def svc(tmp_path):
    db = Db(DB_URL)
    db.apply_migrations()
    task_repo = TaskRepo(db)
    pipeline_repo = PipelineRepo(db)
    service = PipelineService(
        db=db, pipeline_repo=pipeline_repo, task_repo=task_repo,
        tool_repo=ToolRepo(db),
        dispatch_service=DispatchService(db=db, task_repo=task_repo,
                                         tool_repo=ToolRepo(db), event_repo=EventRepo(db)),
        run_event_repo=RunEventRepo(db), data_dir=tmp_path)
    from store.tool_repo import ToolManifest
    tool_repo = ToolRepo(db)
    tool_repo.upsert(ToolManifest.from_toml(
        Path(__file__).parents[1] / "tests" / "fixtures" / "string_reverse" / "tool.toml"),
        path="tests/fixtures/string_reverse")
    service.register("flow.af1.test", "AF1 测试流",
                     [{"tool": "tests.string.reverse", "input": {"text": "x"}}])
    yield service
    for rid in list(getattr(service, "_af1_runs", [])):
        try:
            pipeline_repo.delete_run(rid, drop_tasks=True)
        except Exception:
            pass
    db.close()


def _mk_run(service: PipelineService, file: str, status: str, tasks: int = 1) -> str:
    rid = "p_" + secrets.token_hex(8)
    with service._pipeline_repo._db.pool.connection() as conn:  # noqa: SLF001
        from psycopg.types.json import Json
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af1.test', %s, %s, now())",
            (rid, Json({"file": file}), status))
        for i in range(tasks):
            conn.execute(
                "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status) "
                "VALUES (%s, 'tests.string.reverse', '{}'::jsonb, 1, %s, %s, 'succeeded')",
                ("t_" + secrets.token_hex(8), rid, i))
    service._af1_runs = getattr(service, "_af1_runs", []) + [rid]
    return rid


def test_purge_deletes_tasks_and_failed_attempts(svc, tmp_path):
    """勾删产物：树内 tasks 整删 + 同文件失败 run 连带删（成功 run 保留）。"""
    file = str(tmp_path / "a.pdf")
    ok = _mk_run(svc, file, "succeeded")
    bad1 = _mk_run(svc, file, "failed")
    bad2 = _mk_run(svc, file, "interrupted")
    other = _mk_run(svc, str(tmp_path / "other.pdf"), "failed")  # 不同文件：不动

    out = svc.delete_run(ok, purge_files=True)
    assert out["status"] == "deleted"
    assert sorted(x["id"] for x in out["removed_failed_attempts"]) == sorted([bad1, bad2])
    repo = svc._pipeline_repo
    assert repo.get_run(ok) is None and repo.get_run(bad1) is None and repo.get_run(bad2) is None
    assert repo.get_run(other) is not None  # 其它文件的失败不动
    for rid in (ok, bad1, bad2):
        assert svc._task_repo.list_by_pipeline_run(rid) == []  # tasks 整删无孤儿
    svc._af1_runs = [r for r in svc._af1_runs if r not in (ok, bad1, bad2)]


def test_no_purge_keeps_unbound_tasks(svc, tmp_path):
    """不勾产物：tasks 解绑保留（审计口径），失败尝试也不连带删。"""
    file = str(tmp_path / "b.pdf")
    bad = _mk_run(svc, file, "failed")
    out = svc.delete_run(bad, purge_files=False)
    assert out["removed_failed_attempts"] == []
    with svc._pipeline_repo._db.pool.connection() as conn:  # noqa: SLF001
        n = conn.execute("SELECT count(*) FROM tasks WHERE pipeline_run = %s", (bad,)).fetchone()[0]
        orphans = conn.execute(
            "SELECT count(*) FROM tasks WHERE pipeline_run IS NULL AND handle LIKE 't_%'").fetchone()[0]
    assert n == 0
    assert orphans >= 1  # 解绑后 tasks 还在（孤儿，但不再挡库删除）
    svc._af1_runs = [r for r in svc._af1_runs if r != bad]


def test_rerunnable_zero_after_purge(svc, tmp_path):
    """场景回归：删同文件一次成功 run（勾产物）连带失败尝试后，rerunnable 该文件归零。"""
    file = str(tmp_path / "c.pdf")
    r1 = _mk_run(svc, file, "failed")
    r2 = _mk_run(svc, file, "failed")
    ok = _mk_run(svc, file, "succeeded")
    svc.delete_run(ok, purge_files=True)  # 连带删 r1/r2
    after = svc.rerunnable_runs()
    assert not any(f["file"] == file for f in after["files"])
    svc._af1_runs = [r for r in svc._af1_runs if r not in (ok, r1, r2)]


def test_orphan_task_not_blocking_db_count(svc, tmp_path):
    """孤儿 succeeded task（run 已删、解绑残留）不再计入库引用。"""
    rid = _mk_run(svc, str(tmp_path / "d.pdf"), "succeeded")
    svc._pipeline_repo.delete_run(rid)  # 旧口径：解绑留孤儿 task
    with svc._pipeline_repo._db.pool.connection() as conn:  # noqa: SLF001
        orphans = conn.execute(
            "SELECT count(*) FROM tasks WHERE pipeline_run IS NULL").fetchone()[0]
    assert orphans >= 1
    assert svc._pipeline_repo.db_reference_count("/tmp/x.ocr_results.db") == 0
    svc._af1_runs = [r for r in svc._af1_runs if r != rid]
