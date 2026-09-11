"""06 C4 任务展示归类 e2e：tool/flow/workflow 三分筛选（parent_run_id 上溯根 run join type）。"""

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
DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"

REVERSE_ID = "tests.string.reverse"
FLOW_ID = "test.kind.inner"
WORKFLOW_ID = "test.kind.outer"
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
    pipeline_service = PipelineService(
        db=db, pipeline_repo=pipeline_repo, task_repo=task_repo,
        tool_repo=tool_repo, dispatch_service=dispatch,
        run_event_repo=RunEventRepo(db))
    scheduler = Scheduler(
        db=db, runner=Runner(), task_repo=task_repo, tool_repo=tool_repo,
        event_repo=EventRepo(db), config=load_config(".env"),
        on_task_done=pipeline_service.advance)
    pipeline_service.register(FLOW_ID, "归类内层流", [
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
        {"tool": REVERSE_ID, "input": {"segments": "{{ prev.segments }}"}},
    ])
    pipeline_service.register(WORKFLOW_ID, "归类工作流", [
        {"pipeline": FLOW_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    yield {"svc": pipeline_service, "dispatch": dispatch, "tasks": task_repo,
           "pump": lambda: scheduler.run_once("w-kind")}
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)", (list(IDS),)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))
        conn.execute("DELETE FROM pipelines WHERE id = ANY(%s)", (list(IDS),))


def _drain(stack, times=30):
    for _ in range(times):
        stack["pump"]()
        time.sleep(0.01)


def test_task_kinds_classified(stack):
    """裸工具 / 流任务 / 工作流子任务 各归其类。"""
    stack["dispatch"].submit(REVERSE_ID, {"segments": ["x"]})  # 裸工具
    stack["svc"].run(FLOW_ID, {"segments": ["x"]})             # 普通流
    stack["svc"].run(WORKFLOW_ID, {"segments": ["x"]})         # 工作流（子 run 任务）
    _drain(stack)

    all_tasks = stack["dispatch"].list(limit=100)["tasks"]
    mine = [t for t in all_tasks if t["root_pipeline_id"] in IDS or t["pipeline_run"] is None
            and t["tool_id"] == REVERSE_ID]
    assert mine, "未取到任务"

    tools = stack["dispatch"].list(limit=100, kind="tool")["tasks"]
    assert all(t["task_kind"] == "tool" and t["pipeline_run"] is None for t in tools)
    assert any(t["tool_id"] == REVERSE_ID and t["pipeline_run"] is None for t in tools)

    flows = stack["dispatch"].list(limit=100, kind="flow")["tasks"]
    flow_mine = [t for t in flows if t["root_pipeline_id"] == FLOW_ID]
    assert flow_mine, "flow 归类缺失"
    assert all(t["task_kind"] == "flow" for t in flow_mine)

    wfs = stack["dispatch"].list(limit=100, kind="workflow")["tasks"]
    wf_mine = [t for t in wfs if t["root_pipeline_id"] == WORKFLOW_ID]
    assert wf_mine, "workflow 归类缺失"
    # 子 run 任务的根上溯正确：root_run_id 指向 outer 的 run 而非子 run
    assert all(t["task_kind"] == "workflow" for t in wf_mine)
    assert all(t["pipeline_run"] != t["root_run_id"] for t in wf_mine)


def test_kind_filter_exclusive(stack):
    """三分互斥：同一任务不出现在两类筛选里。"""
    stack["svc"].run(WORKFLOW_ID, {"segments": ["x"]})
    _drain(stack)
    seen: dict[str, set[str]] = {}
    for kind in ("tool", "flow", "workflow"):
        for t in stack["dispatch"].list(limit=100, kind=kind)["tasks"]:
            seen.setdefault(t["handle"], set()).add(kind)
    dup = {h: k for h, k in seen.items() if len(k) > 1}
    assert not dup, f"归类互斥被破坏: {dup}"


def test_workflow_first_step_is_subflow(stack):
    """C1 补测：工作流首步即子流（run 入口直接 spawn）。"""
    run = stack["svc"].run(WORKFLOW_ID, {"segments": ["x"]})
    _drain(stack)
    subs = stack["svc"]._pipeline_repo.get_subruns(run["run_id"])
    assert subs, "首步子流未创建"
    final = stack["svc"]._pipeline_repo.get_run(run["run_id"])
    assert final["status"] == "succeeded"


def test_kind_invalid_rejected(stack):
    from core.errors import ToolUserError
    try:
        stack["dispatch"].list(kind="bogus")
        raised = False
    except ValueError:
        raised = True
    assert raised
