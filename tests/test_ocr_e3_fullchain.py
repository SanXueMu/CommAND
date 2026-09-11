"""E3 三级概念重写：from_spec 转换 + wf.ocr.fullchain 真嵌套注册 e2e（不真跑 LLM）。"""

import json
import time
from pathlib import Path

import pytest

from command_shared.ocr_templates import TemplateStore
from core.errors import ToolDomainError
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
def _ids(request):
    """每测试独立 id 后缀，避免同 id 跨测试删除/注册时序撞车。"""
    tag = request.node.name.split("[")[-1].rstrip("]")[-6:].replace("-", "")[-6:] or "x"
    return f"test.e3.{tag}.inner", f"test.e3.{tag}.outer"


def test_from_spec_converts_and_pads_placeholder(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    from tools.spec.template_from_spec.main import run as from_spec_run
    spec = {"task_spec": {"template": "请按合同提取三线索", "fields": ["甲方", "乙方"],
                          "rules": "以落款为准", "example": {"甲方": "X公司"}},
            "postprocess": [{"name": "h", "code": "def f(r, c):\n    return r"}],
            "view_spec": {"columns": ["甲方"]}}
    out = from_spec_run({"id": "tpl.from.spec", "name": "三线索", "category": "custom",
                         **spec}, None, None)
    assert out["status"] == "created"
    item = TemplateStore(str(tmp_path)).get("tpl.from.spec")
    # template 无 {fields} → 自动补识别字段行
    assert "{fields}" in item["prompt_template"]
    assert "请按合同提取三线索" in item["prompt_template"]
    assert item["fields"] == ["甲方", "乙方"]
    assert item["hooks"][0]["name"] == "h"
    assert item["view_spec"] == {"columns": ["甲方"]}

    with pytest.raises(ToolDomainError, match="template"):
        from_spec_run({"id": "tpl.bad", "name": "x", "category": "custom",
                       "task_spec": {"fields": ["a"]}}, None, None)


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


@pytest.fixture
def stack(tmp_path, monkeypatch, request):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
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
    flow_id, workflow_id = _ids(request)
    yield {"svc": pipeline_service, "repo": pipeline_repo,
           "pump": lambda: scheduler.run_once("w-e3"),
           "flow_id": flow_id, "workflow_id": workflow_id}
    ids = [flow_id, workflow_id]
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = ANY(%s)", (ids,)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))
        conn.execute("DELETE FROM pipelines WHERE id = ANY(%s)", (ids,))


@pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")
def test_workflow_with_subflow_registration_and_type(stack):
    """真嵌套注册 e2e：flow 注册 type=flow，嵌套它的 workflow type=workflow；
    get_definition 下发 type 与步结构（E3 fullchain 同构形状）。"""
    flow_id, workflow_id = stack["flow_id"], stack["workflow_id"]
    stack["svc"].register(flow_id, "内层流", [
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    stack["svc"].register(workflow_id, "外层工作流", [
        {"pipeline": flow_id, "input": {"segments": "{{ input.segments }}"}},
        {"tool": REVERSE_ID, "input": {"segments": "{{ step[0].output.segments }}"}},
    ])
    flow_def = stack["svc"].get(flow_id)
    wf_def = stack["svc"].get(workflow_id)
    assert flow_def["type"] == "flow"
    assert wf_def["type"] == "workflow"
    assert "pipeline" in wf_def["steps"][0]
    assert all(p["id"] != workflow_id for p in stack["svc"].list() if p.get("type") == "flow")


@pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")
def test_workflow_run_end_to_end_subflow(stack):
    """嵌套工作流全链跑通（E3 形状：子流→根步引用子输出）。"""
    flow_id, workflow_id = stack["flow_id"], stack["workflow_id"]
    stack["svc"].register(flow_id, "内层流", [
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    stack["svc"].register(workflow_id, "外层工作流", [
        {"pipeline": flow_id, "input": {"segments": "{{ input.segments }}"}},
        {"tool": REVERSE_ID, "input": {"segments": "{{ step[0].output.segments }}"}},
    ])
    run = stack["svc"].run(workflow_id, {"segments": ["bn"]})
    final = None
    for _ in range(60):
        stack["pump"]()
        final = stack["repo"].get_run(run["run_id"])
        if final["status"] in ("succeeded", "failed", "failed_review"):
            break
        time.sleep(0.02)
    assert final["status"] == "succeeded"
    tasks = {t["step_index"]: t for t in stack["svc"].get_run_tasks(run["run_id"])}
    # 子流 1 次反转（bn→nb），根步再反转（nb→bn）
    assert tasks[1]["output"] == {"segments": ["bn"]}
