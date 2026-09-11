"""06 C4 重跑流 e2e：原 run 留档不可变 / 新 run 独立 / 覆盖生效 / 审计留痕 / workflow 子树重建。"""

import time
from pathlib import Path

import pytest

from core.errors import TaskConflictError, TaskNotFoundError
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
DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"

REVERSE_ID = "tests.string.reverse"
FLOW_ID = "test.rerun.inner"
WORKFLOW_ID = "test.rerun.outer"
IDS = (FLOW_ID, WORKFLOW_ID)


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
    pipeline_service.register(FLOW_ID, "重跑内层流", [
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    pipeline_service.register(WORKFLOW_ID, "重跑工作流", [
        {"pipeline": FLOW_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    yield {"svc": pipeline_service, "repo": pipeline_repo, "audit": run_event_repo,
           "pump": lambda: scheduler.run_once("w-rerun")}
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)", (list(IDS),)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))
        conn.execute("DELETE FROM pipelines WHERE id = ANY(%s)", (list(IDS),))


def _drain_until(stack, run_id, statuses, times=40):
    final = None
    for _ in range(times):
        stack["pump"]()
        final = stack["repo"].get_run(run_id)
        if final["status"] in statuses:
            break
        time.sleep(0.02)
    return final


def test_rerun_flow_creates_independent_run(stack):
    """终态 run 重跑 → 全新 run 成功；原 run 留档不动；审计双向留痕。"""
    original = stack["svc"].run(FLOW_ID, {"segments": ["bn"]})
    orig_id = original["run_id"]
    _drain_until(stack, orig_id, ("succeeded",))

    result = stack["svc"].rerun_run(orig_id)
    new_id = result["run_id"]
    assert new_id != orig_id
    final = _drain_until(stack, new_id, ("succeeded", "failed", "failed_review"))
    assert final["status"] == "succeeded"

    # 原 run 留档不可变（状态不变、input 不变）
    orig = stack["repo"].get_run(orig_id)
    assert orig["status"] == "succeeded"
    assert orig["input"] == {"segments": ["bn"]}

    # 审计：原 run 落 flow_rerun（含 new_run_id）；新 run created 带 rerun_of
    orig_kinds = [(e["kind"], e["detail"]) for e in stack["audit"].list(orig_id)]
    assert any(k == "flow_rerun" and d.get("new_run_id") == new_id for k, d in orig_kinds)
    new_kinds = [(e["kind"], e["detail"]) for e in stack["audit"].list(new_id)]
    assert any(k == "created" and d.get("rerun_of") == orig_id for k, d in new_kinds)


def test_rerun_with_input_override(stack):
    """重跑 input 覆盖生效：新 run 用覆盖值。"""
    original = stack["svc"].run(FLOW_ID, {"segments": ["bn"]})
    _drain_until(stack, original["run_id"], ("succeeded",))
    result = stack["svc"].rerun_run(original["run_id"], input_override={"segments": ["xy"]})
    final = _drain_until(stack, result["run_id"], ("succeeded", "failed"))
    assert final["status"] == "succeeded"
    assert final["input"] == {"segments": ["xy"]}
    tasks = stack["svc"].get_run_tasks(result["run_id"])
    assert tasks[0]["output"] == {"segments": ["yx"]}  # xy 反转 → yx（覆盖确实生效）


def test_rerun_workflow_rebuilds_subtree(stack):
    """workflow 重跑自然重建子 run 树。"""
    original = stack["svc"].run(WORKFLOW_ID, {"segments": ["bn"]})
    orig_id = original["run_id"]
    _drain_until(stack, orig_id, ("succeeded",))
    assert stack["repo"].get_subruns(orig_id), "原 run 无子 run"

    result = stack["svc"].rerun_run(orig_id)
    final = _drain_until(stack, result["run_id"], ("succeeded", "failed"))
    assert final["status"] == "succeeded"
    subs = stack["repo"].get_subruns(result["run_id"])
    assert set(subs) == {0} and subs[0]["status"] == "succeeded"  # 新子树重建于步0
    # 原子树不受影响（run 不可变）
    assert stack["repo"].get_subruns(orig_id)[0]["status"] == "succeeded"


def test_rerun_rejects_non_terminal_run(stack):
    """running/paused 的 run 拒绝重跑（409 语义）。"""
    run = stack["svc"].run(FLOW_ID, {"segments": ["bn"]})
    with pytest.raises(TaskConflictError):
        stack["svc"].rerun_run(run["run_id"])  # 尚未 pump，仍 running
    stack["svc"].abort_run(run["run_id"])
    with pytest.raises(TaskNotFoundError):
        stack["svc"].rerun_run("p_nonexistent00")
