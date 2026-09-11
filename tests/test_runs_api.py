"""job 级运行列表/摘要/删除服务测试（dev PG 不可达则跳过）。"""

import os
from pathlib import Path

import pytest

from config import load_config
from core.errors import TaskConflictError
from core.protocol import ToolManifest
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")
PID = "test.runs.list"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


def _cleanup(db: Db) -> None:
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tasks WHERE pipeline_run IN "
                     "(SELECT id FROM pipeline_runs WHERE pipeline_id = %s)", (PID,))
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = %s", (PID,))
        conn.execute("DELETE FROM pipelines WHERE id = %s", (PID,))


@pytest.fixture
def svc():
    db = Db(DB_URL)
    db.apply_migrations()
    _cleanup(db)
    repo = PipelineRepo(db)
    task_repo = TaskRepo(db)
    tool_repo = ToolRepo(db)
    tool_repo.upsert(
        ToolManifest.from_toml(REPO_ROOT / "tests" / "fixtures" / "string_reverse" / "tool.toml"),
        path="tests/fixtures/string_reverse")
    dispatch = DispatchService(db=db, task_repo=task_repo, tool_repo=tool_repo,
                               event_repo=EventRepo(db))
    service = PipelineService(db=db, pipeline_repo=repo, task_repo=task_repo,
                              tool_repo=tool_repo, dispatch_service=dispatch)
    repo.upsert_definition(PID, "运行列表测试", [{"tool": "tests.string.reverse"}], "测试", "flow", None)
    yield service, repo, task_repo
    _cleanup(db)


def test_run_list_summary_and_delete(svc):
    service, repo, task_repo = svc
    rid = repo.create_run(PID, {"file": "a.xlsx"})
    h1 = task_repo.enqueue("tests.string.reverse", {"file": "a.xlsx"}, pipeline_run=rid, step_index=0)
    task_repo.finish(h1, "succeeded", output={
        "usage_by_model": {"qwen": {"calls": 2, "prompt_tokens": 10, "completion_tokens": 5}},
        "calls": 2, "cache_hits": 3, "review_count": 1, "statuses": ["ok", "review"],
    })
    h2 = task_repo.enqueue("tests.string.reverse", {"file": "a.xlsx"}, pipeline_run=rid, step_index=1)
    task_repo.finish(h2, "failed", error={"kind": "x", "message": "boom"})
    repo.finish_run_forced(rid, "failed", error={"kind": "x", "message": "boom"})

    out = service.list_runs(pipeline_id=PID)
    assert out["total"] == 1
    run = out["runs"][0]
    assert run["id"] == rid and run["status"] == "failed"
    s = run["summary"]
    assert s["usage_by_model"]["qwen"]["calls"] == 2
    assert s["cache_hits"] == 3 and s["review_count"] == 1 and s["ok_count"] == 1
    assert s["steps_done"] == 1

    assert service.delete_run(rid)["status"] == "deleted"
    assert repo.get_run(rid) is None


def test_running_run_cannot_be_deleted(svc):
    service, repo, _ = svc
    rid = repo.create_run(PID, {"file": "b.xlsx"})
    assert repo.get_run(rid)["status"] == "running"
    with pytest.raises(TaskConflictError):
        service.delete_run(rid)
