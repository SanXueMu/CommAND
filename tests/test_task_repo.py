"""task_repo 集成测试：队列状态机 / 并发闸 / 心跳恢复 / 排队取消。"""

import os

import pytest

from core.protocol import IoSection, ResourcesSection, RuntimeSection, ToolManifest, ToolSection
from store.db import Db
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")

TEST_TOOL_ID = "test.dev.echo"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


def _manifest(concurrency: int = 1, max_attempts: int = 2) -> ToolManifest:
    return ToolManifest(
        tool=ToolSection(id=TEST_TOOL_ID, name="测试回声", version="1.0.0"),
        io=IoSection(
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            input_types=["text.raw"],
            output_types=["text.raw"],
        ),
        runtime=RuntimeSection(kind="inproc", entry="main.py:run"),
        resources=ResourcesSection(timeout_s=60, concurrency=concurrency, max_attempts=max_attempts),
    )


@pytest.fixture
def repos():
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    task_repo = TaskRepo(db)
    tool_repo.upsert(_manifest())
    yield task_repo
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tasks WHERE tool_id = %s", (TEST_TOOL_ID,))
        conn.execute("DELETE FROM tools WHERE id = %s", (TEST_TOOL_ID,))
    db.close()


def test_enqueue_claim_finish_roundtrip(repos):
    repo = repos
    handle = repo.enqueue(TEST_TOOL_ID, {"x": 1}, max_attempts=2)
    assert handle.startswith("t_")

    claimed = repo.claim(worker_id="w-test")
    assert claimed is not None and claimed["handle"] == handle
    assert claimed["attempt"] == 1

    repo.heartbeat(handle)
    repo.finish(handle, "succeeded", output={"y": [1, 2]})

    task = repo.get(handle)
    assert task["status"] == "succeeded"
    assert task["output"] == {"y": [1, 2]}
    assert task["finished_at"] is not None


def test_concurrency_gate_blocks_second_claim(repos):
    repo = repos
    h1 = repo.enqueue(TEST_TOOL_ID, {"n": 1})
    h2 = repo.enqueue(TEST_TOOL_ID, {"n": 2})

    first = repo.claim(worker_id="w-test")
    assert first["handle"] == h1

    assert repo.claim(worker_id="w-test") is None, "concurrency=1 应挡住同工具第二条认领"

    repo.finish(h1, "succeeded", output={})
    second = repo.claim(worker_id="w-test")
    assert second is not None and second["handle"] == h2


def test_recover_stale_requeue_then_interrupt(repos):
    repo = repos
    handle = repo.enqueue(TEST_TOOL_ID, {}, max_attempts=2)
    repo.claim(worker_id="w-dead")

    with repo._db.pool.connection() as conn:  # noqa: SLF001 — 测试直接伪造过期心跳
        conn.execute(
            "UPDATE tasks SET heartbeat_at = now() - interval '10 minutes' WHERE handle = %s",
            (handle,),
        )

    result = repo.recover_stale(timeout_s=90)
    assert result["requeued"] >= 1
    task = repo.get(handle)
    assert task["status"] == "queued" and task["attempt"] == 2

    repo.claim(worker_id="w-dead")
    with repo._db.pool.connection() as conn:
        conn.execute(
            "UPDATE tasks SET heartbeat_at = now() - interval '10 minutes' WHERE handle = %s",
            (handle,),
        )
    result = repo.recover_stale(timeout_s=90)
    assert result["interrupted"] >= 1
    task = repo.get(handle)
    assert task["status"] == "interrupted"
    assert task["error"]["code"] == "heartbeat_timeout"


def test_cancel_queued(repos):
    repo = repos
    handle = repo.enqueue(TEST_TOOL_ID, {})
    assert repo.cancel_queued(handle) is True
    assert repo.get(handle)["status"] == "cancelled"
    assert repo.cancel_queued(handle) is False
