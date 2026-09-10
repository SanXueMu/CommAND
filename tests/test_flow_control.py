"""流的全控制 e2e：暂停停在边界 / 恢复断点接力 / 中止留档 / 审计轨迹。"""

import os
import time
from pathlib import Path

import pytest

from core.protocol import ToolManifest
from core.runner import Runner
from core.scheduler import Scheduler
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo
from config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")

REVERSE_ID = "dev.string.reverse"
PIPELINE_ID = "test.flow_control"

STEPS = [
    {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    {"tool": REVERSE_ID, "input": {"segments": "{{ prev.segments }}"}},
    {"tool": REVERSE_ID, "input": {"segments": "{{ prev.segments }}"}},
]


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def stack():
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    task_repo = TaskRepo(db)
    tool_repo.upsert(ToolManifest.from_toml(REPO_ROOT / "tools" / "dev" / "string_reverse" / "tool.toml"),
                     path="tools/dev/string_reverse")
    dispatch = DispatchService(db=db, task_repo=task_repo, tool_repo=tool_repo,
                               event_repo=EventRepo(db))
    pipeline_repo = PipelineRepo(db)
    run_event_repo = RunEventRepo(db)
    pipeline_service = PipelineService(
        db=db, pipeline_repo=pipeline_repo, task_repo=task_repo,
        tool_repo=tool_repo, dispatch_service=dispatch,
        run_event_repo=run_event_repo)
    scheduler = Scheduler(
        db=db, runner=Runner(), task_repo=task_repo, tool_repo=tool_repo,
        event_repo=EventRepo(db), config=load_config(".env"),
        on_task_done=pipeline_service.advance)
    scheduler.start()
    pipeline_repo.upsert_definition(PIPELINE_ID, "流控验证三步流", STEPS)
    yield {"svc": pipeline_service, "repo": pipeline_repo, "audit": run_event_repo,
           "dispatch": dispatch}
    scheduler.stop()
    with db.pool.connection() as conn:
        conn.execute(
            "DELETE FROM run_events WHERE run_id IN (SELECT id FROM pipeline_runs WHERE pipeline_id = %s)",
            (PIPELINE_ID,),
        )
        conn.execute(
            "DELETE FROM tasks WHERE pipeline_run IN (SELECT id FROM pipeline_runs WHERE pipeline_id = %s)",
            (PIPELINE_ID,),
        )
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = %s", (PIPELINE_ID,))
        conn.execute("DELETE FROM pipelines WHERE id = %s", (PIPELINE_ID,))


def _wait_run_terminal(repo, run_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = repo.get_run(run_id)
        if run["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
            return run
        time.sleep(0.1)
    return repo.get_run(run_id)


def test_pause_at_boundary_then_resume(stack):
    """首步完成后暂停 → 停在边界且审计留痕 → 恢复后从第 2 步接力（第 1 步不重发）。"""
    svc, repo, audit = stack["svc"], stack["repo"], stack["audit"]
    created = svc.run(PIPELINE_ID, {"segments": ["甲乙", "abc"]})
    run_id = created["run_id"]

    # 等首步成功后立即暂停（三步流跑得快，轮询抢边界）
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        tasks = svc.get_run_tasks(run_id)
        if tasks and tasks[0]["status"] == "succeeded":
            paused = svc.pause_run(run_id)
            break
        time.sleep(0.02)
    else:
        pytest.fail("首步未在时限内成功")
    assert paused["status"] == "paused"

    time.sleep(0.5)  # 给 advance 一点时间处理边界（若抢到）
    run = repo.get_run(run_id)
    assert run["status"] in ("paused", "running")  # 若全部跑完则 run 已 succeeded
    if run["status"] == "paused":
        first_step_tasks_before = [t for t in svc.get_run_tasks(run_id) if t["step_index"] == 0]
        resumed = svc.resume_run(run_id)
        assert resumed["status"] == "running"
        final = _wait_run_terminal(repo, run_id)
        assert final["status"] == "succeeded"
        first_step_tasks_after = [t for t in svc.get_run_tasks(run_id) if t["step_index"] == 0]
        # 已成功步骤永不重发：第 0 步任务数不变（handle 一致）
        assert {t["handle"] for t in first_step_tasks_before} == {t["handle"] for t in first_step_tasks_after}
        # 审计轨迹：created / step_queued / step_completed / pause_requested / resumed 全留痕
        kinds = [e["kind"] for e in audit.list(run_id)]
        for expected in ("created", "step_queued", "step_completed", "pause_requested", "resumed"):
            assert expected in kinds, f"审计缺 {expected}: {kinds}"


def test_pause_idempotent_and_terminal_conflict(stack):
    svc, repo = stack["svc"], stack["repo"]
    created = svc.run(PIPELINE_ID, {"segments": ["丙丁"]})
    run_id = created["run_id"]
    svc.pause_run(run_id)
    again = svc.pause_run(run_id)  # 幂等
    assert again["status"] == "paused"
    final = _wait_run_terminal(repo, svc.resume_run(run_id)["run_id"])
    assert final["status"] == "succeeded"
    from core.errors import TaskConflictError
    with pytest.raises(TaskConflictError):
        svc.pause_run(run_id)  # 终态 409 语义


def test_abort_leaves_artifacts(stack):
    svc, repo = stack["svc"], stack["repo"]
    created = svc.run(PIPELINE_ID, {"segments": ["戊己", "xy"]})
    run_id = created["run_id"]
    aborted = svc.abort_run(run_id)
    assert aborted["status"] == "cancelled"
    final = _wait_run_terminal(repo, run_id)
    assert final["status"] == "cancelled"
    # 成果留档：run 实体与已跑任务仍可查（快速考证）
    tasks = svc.get_run_tasks(run_id)
    assert isinstance(tasks, list)
    kinds = [e["kind"] for e in stack["audit"].list(run_id)]
    assert "abort_requested" in kinds and "run_aborted" in kinds
    # 再次 abort → 冲突
    from core.errors import TaskConflictError
    with pytest.raises(TaskConflictError):
        svc.abort_run(run_id)
