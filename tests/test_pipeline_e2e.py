"""管线端到端集成测试：两步线性管线 / 失败传播 / 模板断链收口。"""

import os
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
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo
from config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")

REVERSE_ID = "dev.string.reverse"
PIPELINE_ID = "test.double_reverse"


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
    pipeline_service = PipelineService(
        db=db, pipeline_repo=PipelineRepo(db), task_repo=task_repo,
        tool_repo=tool_repo, dispatch_service=dispatch)
    scheduler = Scheduler(
        db=db, runner=Runner(), task_repo=task_repo, tool_repo=tool_repo,
        event_repo=EventRepo(db), config=load_config(".env"),
        on_task_done=pipeline_service.advance)
    yield pipeline_service, scheduler, task_repo
    with db.pool.connection() as conn:
        # 只清理本测试创建的数据（共享 dev 库，禁止宽清理误伤其他管线任务）
        conn.execute(
            "DELETE FROM tasks WHERE pipeline_run IN (SELECT id FROM pipeline_runs WHERE pipeline_id = %s)",
            (PIPELINE_ID,),
        )
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = %s", (PIPELINE_ID,))
        conn.execute("DELETE FROM pipelines WHERE id = %s", (PIPELINE_ID,))
    db.close()


def test_two_step_pipeline_succeeds(stack):
    pipeline_service, scheduler, task_repo = stack
    pipeline_service.register(PIPELINE_ID, "两次反转", steps=[
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
        {"tool": REVERSE_ID, "input": {"segments": "{{ prev.segments }}"}},
    ])

    result = pipeline_service.run(PIPELINE_ID, {"segments": ["你好", "abc"]})
    run_id = result["run_id"]

    assert scheduler.run_once("w-test") is True
    assert scheduler.run_once("w-test") is True
    assert scheduler.run_once("w-test") is False, "两步管线不应产生第三条任务"

    run = pipeline_service._pipeline_repo.get_run(run_id)  # noqa: SLF001
    assert run["status"] == "succeeded"

    tasks = task_repo.list_by_pipeline_run(run_id)
    assert len(tasks) == 2
    assert tasks[0]["status"] == "succeeded" and tasks[0]["output"]["segments"] == ["好你", "cba"]
    assert tasks[1]["status"] == "succeeded"
    assert tasks[1]["input"] == {"segments": ["好你", "cba"]}
    assert tasks[1]["output"]["segments"] == ["你好", "abc"], "两次反转应还原原文"


def test_failed_step_fails_the_run(stack):
    pipeline_service, scheduler, task_repo = stack
    # 次步引用不存在字段 → 解析失败 → run 收口 failed
    pipeline_service.register(PIPELINE_ID, "断链", steps=[
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
        {"tool": REVERSE_ID, "input": {"segments": "{{ prev.not_exist }}"}},
    ])
    result = pipeline_service.run(PIPELINE_ID, {"segments": ["x"]})
    scheduler.run_once("w-test")

    run = pipeline_service._pipeline_repo.get_run(result["run_id"])  # noqa: SLF001
    assert run["status"] == "failed"
    assert "not_exist" in run["error"]["message"]
    tasks = task_repo.list_by_pipeline_run(result["run_id"])
    assert len(tasks) == 1 and tasks[0]["status"] == "succeeded", "断链发生在入队次步时，首步本身成功"


def test_run_idempotent_advance(stack):
    pipeline_service, scheduler, task_repo = stack
    pipeline_service.register(PIPELINE_ID, "幂等", steps=[
        {"tool": REVERSE_ID, "input": {"segments": "{{ input.segments }}"}},
    ])
    result = pipeline_service.run(PIPELINE_ID, {"segments": ["a"]})
    scheduler.run_once("w-test")

    task = task_repo.list_by_pipeline_run(result["run_id"])[0]
    pipeline_service.advance(task)  # 已收口后再推进 → 无副作用
    run = pipeline_service._pipeline_repo.get_run(result["run_id"])  # noqa: SLF001
    assert run["status"] == "succeeded"
