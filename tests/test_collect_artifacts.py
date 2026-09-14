"""产物收集服务测试：scope=final/all、真实存在校验、data_dir 边界、去重（dev PG 不可达则跳过）。"""

from pathlib import Path

import pytest

from core.errors import TaskNotFoundError
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
PID = "test.collect.artifacts"

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
    service = PipelineService(db=db, pipeline_repo=repo, task_repo=task_repo, tool_repo=tool_repo,
                              dispatch_service=dispatch, run_event_repo=RunEventRepo(db),
                              data_dir=tmp_path)
    repo.upsert_definition(PID, "产物收集测试",
                           [{"tool": "tests.string.reverse"}, {"tool": "tests.string.reverse"}],
                           "测试", "flow", None)
    yield service, repo, task_repo, tmp_path
    _cleanup(db)


def _write(tmp_path: Path, rel: str, payload: bytes = b"X") -> Path:
    target = tmp_path / "outputs" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def test_collect_artifacts_scope_and_filters(svc):
    service, repo, task_repo, tmp_path = svc
    rid = repo.create_run(PID, {"file": "a.docx"})
    mid = _write(tmp_path, "h1/可搜索.pdf")
    final = _write(tmp_path, "h1/译文.docx")
    outside = tmp_path.parent / "外部文件.docx"
    outside.write_bytes(b"OUT")
    missing = tmp_path / "outputs" / "h1" / "不存在.docx"

    h0 = task_repo.enqueue("tests.string.reverse", {"file": "a.docx"}, pipeline_run=rid, step_index=0)
    task_repo.finish(h0, "succeeded", output={
        "layered_file": str(mid), "layered_name": "可搜索.pdf",
        "path": str(missing),          # 不存在 → 排除
        "name": "无关.docx",            # 纯名称键 → 排除
        "dump": str(_write(tmp_path, "h1/stat.json")),  # 非文档后缀 → 排除
        "escape": str(outside),        # data_dir 外 → 排除
    })
    h1 = task_repo.enqueue("tests.string.reverse", {"file": "a.docx"}, pipeline_run=rid, step_index=1)
    task_repo.finish(h1, "succeeded", output={
        "path": str(final), "name": "译文.docx",
        "render_file": str(final),     # 同文件两个键 → 只收一次
    })

    final_only = service.collect_run_artifacts(rid, "final")
    assert [a["name"] for a in final_only] == ["译文.docx"]
    assert final_only[0]["step"] == 1 and final_only[0]["size"] == 1

    everything = service.collect_run_artifacts(rid, "all")
    assert {a["name"] for a in everything} == {"可搜索.pdf", "译文.docx"}
    assert [a["step"] for a in everything] == [0, 1], "按步序返回"
    assert all(str(tmp_path) in a["path"] for a in everything)

    with pytest.raises(TaskNotFoundError):
        service.collect_run_artifacts("p_不存在", "final")


def test_collect_artifacts_empty_when_no_successful_step(svc):
    service, repo, task_repo, tmp_path = svc
    rid = repo.create_run(PID, {"file": "b.docx"})
    handle = task_repo.enqueue("tests.string.reverse", {"file": "b.docx"}, pipeline_run=rid, step_index=0)
    task_repo.finish(handle, "failed", error={"kind": "x", "message": "boom"})
    assert service.collect_run_artifacts(rid, "final") == []
