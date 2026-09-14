"""E2 任务级暂停全链路：工具退出码 4 → 任务 paused / run paused（不级联失败）→
修好源文件后 resume 从该步续跑 → 成功。用 tests.string.pause 演示工具与真 DB（dev PG）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from config import load_config
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

REPO_ROOT = Path(__file__).resolve().parent.parent
from tests._dbutil import db_reachable
DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"

PAUSE_ID = "tests.string.pause"
FLOW_ID = "test.pause.flow"


def _db_reachable() -> bool:
    return db_reachable(DB_URL)


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def stack(tmp_path):
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    task_repo = TaskRepo(db)
    tool_repo.upsert(
        ToolManifest.from_toml(REPO_ROOT / "tests" / "fixtures" / "string_pause" / "tool.toml"),
        path="tests/fixtures/string_pause")
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
    pipeline_service.register(FLOW_ID, "暂停演示流", [
        {"tool": PAUSE_ID, "input": {"file": "{{ input.file }}"}},
    ])
    yield {"svc": pipeline_service, "repo": pipeline_repo, "audit": run_event_repo,
           "tasks": task_repo, "pump": lambda: scheduler.run_once("w-pause"), "tmp": tmp_path}
    with db.pool.connection() as conn:
        run_ids = [r[0] for r in conn.execute(
            "SELECT id FROM pipeline_runs WHERE pipeline_id = %s", (FLOW_ID,)).fetchall()]
        if run_ids:
            conn.execute("DELETE FROM run_events WHERE run_id = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM tasks WHERE pipeline_run = ANY(%s)", (run_ids,))
            conn.execute("DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,))
        conn.execute("DELETE FROM pipelines WHERE id = %s", (FLOW_ID,))


def _run(svc, file: Path) -> str:
    return svc.run(FLOW_ID, {"file": str(file)})["run_id"]


def test_pause_then_resume_same_step(stack):
    src = stack["tmp"] / "src.txt"
    src.write_text("PAUSE\nhello\nworld\n", encoding="utf-8")
    run_id = _run(stack["svc"], src)

    stack["pump"]()  # 第一步执行 → 退出码 4
    run = stack["repo"].get_run(run_id)
    assert run["status"] == "paused", run
    tasks = stack["svc"].get_run_tasks(run_id)
    assert [t["status"] for t in tasks] == ["paused"]
    assert tasks[0]["error"]["kind"] == "pause"
    assert "人工介入" in tasks[0]["error"]["message"]

    kinds = [e["kind"] for e in stack["audit"].list(run_id, limit=50)]
    assert "step_paused" in kinds
    assert "step_failed" not in kinds  # 暂停不是失败，绝不级联收口

    # 修好源文件（路径不变）→ resume 从该步重发
    src.write_text("hello\nworld\n", encoding="utf-8")
    stack["svc"].resume_run(run_id)
    stack["pump"]()

    run = stack["repo"].get_run(run_id)
    assert run["status"] == "succeeded", run
    # 同一 handle 再次尝试：新任务覆盖 paused 任务成为该步终态
    tasks = stack["svc"].get_run_tasks(run_id)
    assert tasks[-1]["status"] == "succeeded"
    assert tasks[-1]["output"]["segments"] == ["olleh", "dlrow"]


def test_pause_does_not_consume_retries(stack):
    """暂停与「失败重试」正交：max_attempts=1 也不会因暂停被判定失败。"""
    src = stack["tmp"] / "src.txt"
    src.write_text("PAUSE\nx\n", encoding="utf-8")
    run_id = _run(stack["svc"], src)
    stack["pump"]()
    for _ in range(3):  # 再空转几轮，不得被重试或收口
        stack["pump"]()
    run = stack["repo"].get_run(run_id)
    assert run["status"] == "paused"
    tasks = stack["svc"].get_run_tasks(run_id)
    assert [t["status"] for t in tasks] == ["paused"]


def test_skip_pause_tool_raises_task_pause():
    """file.skip.pause：刻意不处理的文件（如 PPT）→ 抛 ToolPauseError（任务落 paused 留档）。"""
    import types

    from core.errors import ToolPauseError
    from tools.file.skip_pause import main as skip_main

    with pytest.raises(ToolPauseError, match="PPT"):
        skip_main.run({"file": "演讲.pptx", "reason": "PPT 暂不支持翻译"},
                      types.SimpleNamespace(handle="h"), lambda e: None)
