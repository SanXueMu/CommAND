"""job 级运行列表/摘要/删除服务测试（dev PG 不可达则跳过）。"""

from pathlib import Path

import pytest

from config import load_config
from core.protocol import ToolManifest
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from store.db import Db
from store.event_repo import EventRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo
from tests._dbutil import DEFAULT_DB_URL as DB_URL, db_reachable

REPO_ROOT = Path(__file__).resolve().parent.parent
PID = "test.runs.list"

pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


def _cleanup(db: Db) -> None:
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM run_events WHERE run_id IN "
                     "(SELECT id FROM pipeline_runs WHERE pipeline_id = %s)", (PID,))
        conn.execute("DELETE FROM tasks WHERE pipeline_run IN "
                     "(SELECT id FROM pipeline_runs WHERE pipeline_id = %s)", (PID,))
        conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = %s", (PID,))
        conn.execute("DELETE FROM pipelines WHERE id = %s", (PID,))


@pytest.fixture
def svc(tmp_path):
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
                              tool_repo=tool_repo, dispatch_service=dispatch,
                              run_event_repo=RunEventRepo(db), data_dir=tmp_path)
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


def test_delete_run_with_audit_events(svc):
    """回归：带审计事件的 run 删除不再 500（011 前必 ForeignKeyViolation）。"""
    service, repo, task_repo = svc
    rid = repo.create_run(PID, {"file": "c.xlsx"})
    events = RunEventRepo(service._db)
    for kind in ("created", "step_queued", "step_started", "step_completed"):
        events.append(rid, None, kind)
    with service._db.pool.connection() as conn:
        (before,) = conn.execute(
            "SELECT count(*) FROM run_events WHERE run_id = %s", (rid,)).fetchone()
    assert before == 4
    assert service.delete_run(rid)["status"] == "deleted"
    assert repo.get_run(rid) is None
    with service._db.pool.connection() as conn:
        (after,) = conn.execute(
            "SELECT count(*) FROM run_events WHERE run_id = %s", (rid,)).fetchone()
    assert after == 0


def test_delete_run_purges_artifacts_with_child_runs(svc):
    """删除任务连带清除产物（含子 run 的事件与产物）；purge_files=false 则保留文件。"""
    service, repo, task_repo = svc
    rid = repo.create_run(PID, {"file": "d.xlsx"})
    h1 = task_repo.enqueue("tests.string.reverse", {"file": "d.xlsx"},
                           pipeline_run=rid, step_index=0)
    child = repo.create_run(PID, {"file": "d.xlsx"}, parent_run_id=rid, parent_step_index=0)
    grand = repo.create_run(PID, {"file": "d.xlsx"}, parent_run_id=child, parent_step_index=0)
    h2 = task_repo.enqueue("tests.string.reverse", {"file": "d.xlsx"},
                           pipeline_run=grand, step_index=0)
    RunEventRepo(service._db).append(rid, h1, "created")
    RunEventRepo(service._db).append(child, h2, "created")
    RunEventRepo(service._db).append(grand, h2, "created")
    for handle in (h1, h2):
        d = service._data_dir / "outputs" / handle
        (d / "nested").mkdir(parents=True)
        (d / "译文.pdf").write_bytes(b"x" * 100)
        (d / "nested" / "tmp.json").write_bytes(b"y" * 50)

    out = service.delete_run(rid, purge_files=True)
    assert out["status"] == "deleted" and out["purge_files"] is True
    assert out["files_removed"] == 4 and out["bytes_freed"] == 300 and out["dirs_removed"] == 2
    assert repo.get_run(rid) is None and repo.get_run(child) is None
    assert repo.get_run(grand) is None  # 递归删除整棵子树（此列即 500 的多层场景）
    for handle in (h1, h2):
        assert not (service._data_dir / "outputs" / handle).exists()

    rid2 = repo.create_run(PID, {"file": "e.xlsx"})
    h3 = task_repo.enqueue("tests.string.reverse", {"file": "e.xlsx"},
                           pipeline_run=rid2, step_index=0)
    keep = service._data_dir / "outputs" / h3
    keep.mkdir(parents=True)
    (keep / "留档.pdf").write_bytes(b"z")
    out2 = service.delete_run(rid2, purge_files=False)
    assert out2["files_removed"] == 0 and keep.exists()


def test_delete_running_run_aborts_then_deletes(svc):
    """运行中的 run 不再 409：自动中止后删除，并清理其排队任务。"""
    service, repo, task_repo = svc
    rid = repo.create_run(PID, {"file": "b.xlsx"})
    task_repo.enqueue("tests.string.reverse", {"file": "b.xlsx"},
                      pipeline_run=rid, step_index=0)
    assert repo.get_run(rid)["status"] == "running"
    out = service.delete_run(rid)
    assert out["status"] == "deleted" and out["aborted"] is True
    assert out["pending_tasks"] == []
    assert repo.get_run(rid) is None
