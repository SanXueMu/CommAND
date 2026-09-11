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

REVERSE_ID = "tests.string.reverse"
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
    tool_repo.upsert(ToolManifest.from_toml(REPO_ROOT / "tests" / "fixtures" / "string_reverse" / "tool.toml"),
                     path="tests/fixtures/string_reverse")
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
    pipeline_repo.upsert_definition(PIPELINE_ID, "流控验证三步流", STEPS)
    yield {"svc": pipeline_service, "repo": pipeline_repo, "audit": run_event_repo,
           "dispatch": dispatch, "pump": lambda: scheduler.run_once("w-flow-ctl")}
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


def _pump_until(stack, run_id, statuses, timeout=10.0):
    """手动泵 scheduler（run_once），直到 run 进入期望状态（不启动后台线程，避免共享库竞态）。

    先泵后查：确保至少推进一次（pause 场景下状态在泵前就成立，需靠泵驱动到边界）。
    """
    repo = stack["repo"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stack["pump"]()
        run = repo.get_run(run_id)
        if run["status"] in statuses:
            return run
        time.sleep(0.02)
    return repo.get_run(run_id)


def _wait_run_terminal(stack, run_id, timeout=10.0):
    return _pump_until(stack, run_id,
                       ("succeeded", "failed", "cancelled", "interrupted"), timeout)


def test_pause_at_boundary_then_resume(stack):
    """首步完成后暂停 → 停在边界且审计留痕 → 恢复后从第 2 步接力（第 1 步不重发）。"""
    svc, repo, audit = stack["svc"], stack["repo"], stack["audit"]
    created = svc.run(PIPELINE_ID, {"segments": ["甲乙", "abc"]})
    run_id = created["run_id"]

    # 确定性边界：先暂停（step0 仍在队列），泵跑 step0 → advance 派发门必停边界
    assert svc.pause_run(run_id)["status"] == "paused"
    run = _pump_until(stack, run_id, {"paused"})
    assert run["status"] == "paused"
    assert run["progress"] == 1, "应停在 step1 派发前"
    tasks_mid = svc.get_run_tasks(run_id)
    assert [t["step_index"] for t in tasks_mid] == [0], "边界处只应有 step0 任务"
    step0_before = {t["handle"] for t in tasks_mid}

    resumed = svc.resume_run(run_id)
    assert resumed["status"] == "running"
    final = _wait_run_terminal(stack, run_id)
    assert final["status"] == "succeeded"
    step0_after = {t["handle"] for t in svc.get_run_tasks(run_id) if t["step_index"] == 0}
    assert step0_after == step0_before, "已成功步骤永不重发"
    kinds = [e["kind"] for e in audit.list(run_id)]
    for expected in ("created", "step_queued", "step_completed",
                     "pause_requested", "paused_at_boundary", "resumed"):
        assert expected in kinds, f"审计缺 {expected}: {kinds}"


def test_pause_idempotent_and_terminal_conflict(stack):
    svc, repo = stack["svc"], stack["repo"]
    created = svc.run(PIPELINE_ID, {"segments": ["丙丁"]})
    run_id = created["run_id"]
    from core.errors import TaskConflictError
    with pytest.raises(TaskConflictError):
        svc.rerun_step(run_id, 0)  # running 中拒绝重跑（确定性：无人泵则必为 running）
    svc.pause_run(run_id)
    again = svc.pause_run(run_id)  # 幂等
    assert again["status"] == "paused"
    final = _wait_run_terminal(stack, svc.resume_run(run_id)["run_id"])
    assert final["status"] == "succeeded"
    with pytest.raises(TaskConflictError):
        svc.pause_run(run_id)  # 终态 409 语义


def test_abort_leaves_artifacts(stack):
    svc, repo = stack["svc"], stack["repo"]
    created = svc.run(PIPELINE_ID, {"segments": ["戊己", "xy"]})
    run_id = created["run_id"]
    aborted = svc.abort_run(run_id)
    assert aborted["status"] == "cancelled"
    final = _wait_run_terminal(stack, run_id)
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


def test_rerun_step_with_override(stack):
    """三步流完成后 rerun 第 1 步（override 换参）→ 第 1/2 步重跑、第 0 步不动、旧任务留档。"""
    svc, repo, audit = stack["svc"], stack["repo"], stack["audit"]
    created = svc.run(PIPELINE_ID, {"segments": ["甲乙", "abc"]})
    run_id = created["run_id"]
    final = _wait_run_terminal(stack, run_id)
    assert final["status"] == "succeeded"
    tasks_before = svc.get_run_tasks(run_id)
    step0_handles = {t["handle"] for t in tasks_before if t["step_index"] == 0}

    rerun = svc.rerun_step(run_id, 1, override={"segments": ["丙丁"]})
    assert rerun["status"] == "running"
    refinal = _wait_run_terminal(stack, run_id)
    assert refinal["status"] == "succeeded"

    tasks_after = svc.get_run_tasks(run_id)
    # 第 0 步永不重发
    assert {t["handle"] for t in tasks_after if t["step_index"] == 0} == step0_handles
    # 第 1 步出现新任务且输出反映 override；旧任务留档（历史不撒谎）
    step1 = [t for t in tasks_after if t["step_index"] == 1]
    assert len(step1) >= 2, "旧任务应留档"
    latest_output = sorted(step1, key=lambda t: t["created_at"])[-1]["output"]
    assert latest_output["segments"] == ["丁丙"], "override 后的反转结果"
    # 审计：rerun_requested + override_applied + step_rerun
    kinds = [e["kind"] for e in audit.list(run_id)]
    for expected in ("rerun_requested", "override_applied", "step_rerun"):
        assert expected in kinds, f"审计缺 {expected}: {kinds}"


def test_abort_step_conflicts(stack):
    svc, repo = stack["svc"], stack["repo"]
    created = svc.run(PIPELINE_ID, {"segments": ["戊己"]})
    run_id = created["run_id"]
    _wait_run_terminal(stack, run_id)
    from core.errors import TaskConflictError, TaskNotFoundError
    with pytest.raises(TaskNotFoundError):
        svc.abort_step(run_id, 9)  # 无任务步骤
    with pytest.raises(TaskConflictError):
        svc.abort_step(run_id, 0)  # 已 succeeded 不可中止
    # succeeded 状态允许 rerun（复活）—— 由 test_rerun_step_with_override 覆盖
