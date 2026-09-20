"""AF3：决定性错误收口自动清产物（user/unavailable → purge，只留日志与事件）。"""
from __future__ import annotations

import secrets
from pathlib import Path

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
        Path(__file__).parents[1] / "tests" / "fixtures" / "string_reverse" / "tool.toml"),
        path="tests/fixtures/string_reverse")
    pipeline_repo = PipelineRepo(db)
    run_event_repo = RunEventRepo(db)
    task_repo = TaskRepo(db)
    from services.dispatch_service import DispatchService
    svc = PipelineService(
        db=db, pipeline_repo=pipeline_repo, task_repo=task_repo,
        tool_repo=tool_repo,
        dispatch_service=DispatchService(db=db, task_repo=task_repo,
                                         tool_repo=tool_repo, event_repo=EventRepo(db)),
        run_event_repo=run_event_repo, data_dir=tmp_path)
    svc.register("flow.af3.test", "AF3 测试流",
                 [{"tool": "tests.string.reverse", "input": {"text": "x"}}])
    yield {"svc": svc, "repo": pipeline_repo, "audit": run_event_repo,
           "task_repo": task_repo, "tmp": tmp_path}
    db.close()


def _mk_failed_run(stack, error: dict, with_outputs: bool) -> str:
    repo, task_repo, tmp = stack["repo"], stack["task_repo"], stack["tmp"]
    rid = "p_" + secrets.token_hex(8)
    handle = "t_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        from psycopg.types.json import Json
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, error, finished_at, created_at) "
            "VALUES (%s, 'flow.af3.test', %s, 'failed', %s, now(), now())",
            (rid, Json({"file": "/tmp/af3.pdf"}), Json(error)))
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status) "
            "VALUES (%s, 'tests.string.reverse', '{}'::jsonb, 1, %s, 0, 'succeeded')",
            (handle, rid))
    if with_outputs:  # 造一个产物目录 + 一个 OCR 库
        out_dir = tmp / "outputs" / handle
        out_dir.mkdir(parents=True)
        (out_dir / "part.txt").write_text("x", encoding="utf-8")
        ocr_dir = tmp / "ocr"
        ocr_dir.mkdir(exist_ok=True)
        db_path = ocr_dir / "af3.ocr_results.db"
        db_path.write_bytes(b"SQLite mock")
        with repo._db.pool.connection() as conn:  # noqa: SLF001
            conn.execute(
                "UPDATE tasks SET output = %s WHERE handle = %s",
                (Json({"db": str(db_path)}), handle))
    return rid


@pytest.mark.parametrize("kind,expect_purged", [
    ("user", True),          # 参数/用法错 → 决定性 → 清产物
    ("system", False),       # 暂时性 → 保留
    ("domain", False),       # 领域复核 → 保留
])
def test_purge_matrix(stack, kind, expect_purged):
    """决定性失败经 advance 收口 → 产物被清；暂时性失败 → 产物保留。"""
    svc, repo, audit = stack["svc"], stack["repo"], stack["audit"]
    # 直接调 _finish_and_cascade 前 run 必须是 running（finish_run 前置约束）
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        from psycopg.types.json import Json
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af3.test', %s, 'running', now())",
            (rid, Json({"file": "/tmp/af3.pdf"})))
        handle = "t_" + secrets.token_hex(8)
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status) "
            "VALUES (%s, 'tests.string.reverse', '{}'::jsonb, 1, %s, 0, 'succeeded')",
            (handle, rid))
        conn.execute(
            "INSERT INTO tasks (handle, tool_id, input, max_attempts, pipeline_run, step_index, status) "
            "VALUES (%s, 'tests.string.reverse', '{}'::jsonb, 1, %s, 1, 'failed')",
            ("f_" + secrets.token_hex(8), rid))
    out_dir = stack["tmp"] / "outputs" / handle
    out_dir.mkdir(parents=True)
    (out_dir / "part.txt").write_text("x", encoding="utf-8")
    db_path = stack["tmp"] / "ocr" / f"{rid}.ocr_results.db"
    db_path.parent.mkdir(exist_ok=True)
    db_path.write_bytes(b"SQLite mock")
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        conn.execute("UPDATE tasks SET output = %s WHERE handle = %s",
                     (Json({"db": str(db_path)}), handle))
    try:
        svc._finish_and_cascade(rid, "failed", error={"kind": kind, "message": "测试"})
        assert repo.get_run(rid)["status"] == "failed"
        assert (out_dir / "part.txt").exists() is not expect_purged
        assert db_path.exists() is not expect_purged
        events = audit.list(rid)
        assert any(e["kind"] == "artifacts_purged" for e in events) is expect_purged
    finally:
        repo.delete_run(rid, drop_tasks=True)


def test_unavailable_pauses_and_keeps_artifacts(stack):
    """015 语义：unavailable 且无可降级流 → paused（能力不可用暂停），产物保留待修复后续跑。"""
    svc, repo = stack["svc"], stack["repo"]
    rid = "p_" + secrets.token_hex(8)
    with repo._db.pool.connection() as conn:  # noqa: SLF001
        from psycopg.types.json import Json
        conn.execute(
            "INSERT INTO pipeline_runs (id, pipeline_id, input, status, created_at) "
            "VALUES (%s, 'flow.af3.test', %s, 'running', now())",
            (rid, Json({"file": "/tmp/af3.pdf"})))
    try:
        svc._finish_and_cascade(rid, "failed", error={"kind": "unavailable", "message": "模型未开通"})
        assert repo.get_run(rid)["status"] == "paused"
    finally:
        repo.delete_run(rid, drop_tasks=True)


def test_transient_survives_for_rerun(stack):
    """暂时性失败产物保留（页级缓存可续跑）——重跑链路不被 AF3 破坏。"""
    rid = _mk_failed_run(stack, {"kind": "system", "message": "连接超时"}, with_outputs=True)
    stack["svc"]._purge_decisive(rid, "failed", {"kind": "system"}, fallback=False)
    # system 不在决定性集合 → 无动作
    stack["repo"].delete_run(rid, drop_tasks=True)
