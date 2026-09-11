"""06 C1 嵌套执行 e2e（07 设计验收）：子 run 实体化 / 级联收口 / 子输出入父 history /
失败级联 / abort 递归 / snapshot 子 run 标记 / register 限深与 type 变更校验。"""

import time
from pathlib import Path

import pytest

from core.errors import ToolNotFoundError, ToolUserError
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
FLOW_ID = "test.nested.inner"
WORKFLOW_ID = "test.nested.outer"

# inner：普通流（两次反转）
INNER_STEPS = [
    {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    {"tool": REVERSE_ID, "input": {"segments": "{{ prev.segments }}"}},
]
# outer：工作流（tool → 子流 → tool，末步引用子流步输出）
OUTER_STEPS = [
    {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    {"pipeline": FLOW_ID, "input": {"segments": "{{ prev.segments }}"}},
    {"tool": REVERSE_ID, "input": {"segments": "{{ step[1].output.segments }}"}},
]

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
    pipeline_service.register(FLOW_ID, "内层普通流", INNER_STEPS)
    pipeline_service.register(WORKFLOW_ID, "外层工作流", OUTER_STEPS)
    yield {"svc": pipeline_service, "repo": pipeline_repo, "audit": run_event_repo,
           "tasks": task_repo, "pump": lambda: scheduler.run_once("w-nested")}
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)", (list(IDS),)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))
        conn.execute("DELETE FROM pipelines WHERE id = ANY(%s)", (list(IDS),))


def _pump_until(stack, run_id, statuses, timeout=10.0):
    repo = stack["repo"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stack["pump"]()
        run = repo.get_run(run_id)
        if run["status"] in statuses:
            return run
        time.sleep(0.02)
    return repo.get_run(run_id)


def test_nested_e2e_cascade_and_output(stack):
    """tool → 子流 → tool 全链：子 run 实体化、级联收口、子输出经 step[1] 入父末步。"""
    run = stack["svc"].run(WORKFLOW_ID, {"segments": ["bn"]})
    run_id = run["run_id"]
    final = _pump_until(stack, run_id, ("succeeded", "failed", "failed_review"))
    assert final["status"] == "succeeded"

    # 子 run 实体化且成功
    subruns = stack["repo"].get_subruns(run_id)
    assert 1 in subruns and subruns[1]["status"] == "succeeded"
    assert subruns[1]["pipeline_id"] == FLOW_ID

    # 子 run 输出可被父 history 消费：共 4 次反转（步0 + inner 两步 + 末步）= 还原
    tasks = {t["step_index"]: t for t in stack["svc"].get_run_tasks(run_id)}
    assert tasks[2]["output"] == {"segments": ["bn"]}
    assert tasks[2]["input"] == {"segments": ["nb"]}  # step[1].output.segments = 子流末步输出（inner 步1 反转 bn→nb）

    # 审计因果链：subrun_created / subrun_finished 均落父
    kinds = [e["kind"] for e in stack["audit"].list(run_id)]
    assert kinds.count("subrun_created") == 1
    assert kinds.count("subrun_finished") == 1


def test_subrun_failure_cascades_to_parent(stack):
    """子 run 中途任务失败 → 父同状态收口（部件失败=整流失败）。"""
    run = stack["svc"].run(WORKFLOW_ID, {"segments": ["bn"]})
    run_id = run["run_id"]
    sub_run_id = _pump_until_spawned(stack, run_id)
    # 直改子 run 首任务为 failed，模拟工具执行失败
    handle = _first_handle(stack, sub_run_id)
    stack["tasks"].finish(handle, "failed", error={"kind": "system", "message": "boom"})
    # finish 不走 scheduler 钩子——手动重放 advance（与 S2b 恢复同路径）
    task = next(t for t in stack["svc"].get_run_tasks(sub_run_id) if t["handle"] == handle)
    stack["svc"].advance(task)
    final = _pump_until(stack, run_id, ("succeeded", "failed", "failed_review"))
    assert final["status"] == "failed"
    assert stack["repo"].get_run(sub_run_id)["status"] == "failed"


def _pump_until_spawned(stack, parent_run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stack["pump"]()
        subruns = stack["repo"].get_subruns(parent_run_id)
        if subruns:
            return subruns[1]["id"]
        time.sleep(0.02)
    raise AssertionError("子 run 未创建")


def _first_handle(stack, run_id):
    tasks = stack["tasks"].list_by_pipeline_run(run_id)
    assert tasks, "子 run 无任务"
    return tasks[0]["handle"]


def test_parent_abort_recurses_to_subrun(stack):
    """父 abort → 活跃子 run 递归 cancelled（父终止=整树终止）。"""
    run = stack["svc"].run(WORKFLOW_ID, {"segments": ["bn"]})
    run_id = run["run_id"]
    sub_run_id = _pump_until_spawned(stack, run_id)
    result = stack["svc"].abort_run(run_id)
    assert result["status"] == "cancelled"
    assert stack["repo"].get_run(sub_run_id)["status"] == "cancelled"


def test_snapshot_marks_subrun(stack):
    """snapshot 的 pipeline 步带 subrun 标记（StepTrack 下钻入口）。"""
    run = stack["svc"].run(WORKFLOW_ID, {"segments": ["bn"]})
    run_id = run["run_id"]
    _pump_until(stack, run_id, ("succeeded", "failed", "failed_review"))
    snap = stack["svc"].run_snapshot(run_id)
    entry = snap["steps"][1]
    assert entry["pipeline"] == FLOW_ID
    assert entry["subrun"]["status"] == "succeeded"
    assert entry["tool"] is None


def test_register_rejects_workflow_nesting(stack):
    """限深两层：workflow 引用 workflow → 422。"""
    wf2 = "test.nested.outer2"
    with pytest.raises(ToolUserError, match="只能引用普通流"):
        stack["svc"].register(wf2, "禁止三层", [
            {"pipeline": WORKFLOW_ID, "input": {}}])
    with pytest.raises(ToolNotFoundError):
        stack["svc"].register(wf2, "引用未注册流", [
            {"pipeline": "test.nested.ghost", "input": {}}])
    with pytest.raises(ToolUserError, match="只能其一"):
        stack["svc"].register(wf2, "双键拒绝", [
            {"tool": REVERSE_ID, "pipeline": FLOW_ID, "input": {}}])


def test_register_rejects_type_change_and_flow_refuses_pipeline(stack):
    """type 变更禁止（P6）；普通流引用子流同样拒绝。"""
    with pytest.raises(ToolUserError, match="流类型不可变更"):
        stack["svc"].register(FLOW_ID, "内层改工作流", [
            {"pipeline": FLOW_ID, "input": {}}])  # 引用合法 flow → ptype=workflow ≠ 存量 flow
    with pytest.raises(ToolUserError, match="流类型不可变更"):
        stack["svc"].register(WORKFLOW_ID, "工作流降普通流", [
            {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}}])


def test_flow_level_input_schema_roundtrip(stack):
    """流级 input_schema 注册下发（06：FlowRunner 从猜键变声明驱动）。"""
    schema = {"type": "object", "properties": {"segments": {"type": "array", "title": "文本段落"}}}
    stack["svc"].register(FLOW_ID, "内层普通流", INNER_STEPS, input_schema=schema)
    got = stack["svc"].get(FLOW_ID)
    assert got["input_schema"] == schema
    assert got["type"] == "flow"
