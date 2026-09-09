"""dispatch_service 集成测试：信封校验拦截 / 入队 / 查询 / 排队取消。"""

import os

import pytest

from core.errors import (
    TaskConflictError,
    TaskNotFoundError,
    ToolNotFoundError,
    ToolUserError,
)
from core.protocol import IoSection, ResourcesSection, RuntimeSection, ToolManifest, ToolSection
from services.dispatch_service import DispatchService
from store.db import Db
from store.event_repo import EventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")

TEST_TOOL_ID = "test.dev.gate"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def service():
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    tool_repo.upsert(
        ToolManifest(
            tool=ToolSection(id=TEST_TOOL_ID, name="校验门", version="1.0.0"),
            io=IoSection(
                input_schema={
                    "type": "object",
                    "required": ["segments"],
                    "properties": {"segments": {"type": "array", "items": {"type": "string"}}},
                },
                output_schema={"type": "object"},
                input_types=["text.raw[]"],
                output_types=["text.raw[]"],
            ),
            runtime=RuntimeSection(kind="inproc", entry="main.py:run"),
            resources=ResourcesSection(timeout_s=60, concurrency=1, max_attempts=1),
        )
    )
    svc = DispatchService(
        db=db,
        task_repo=TaskRepo(db),
        tool_repo=tool_repo,
        event_repo=EventRepo(db),
    )
    yield svc
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tasks WHERE tool_id = %s", (TEST_TOOL_ID,))
        conn.execute("DELETE FROM tools WHERE id = %s", (TEST_TOOL_ID,))
    db.close()


def test_submit_rejects_schema_violation(service):
    with pytest.raises(ToolUserError):
        service.submit(TEST_TOOL_ID, {"segments": "不是数组"})


def test_submit_rejects_unknown_tool(service):
    with pytest.raises(ToolNotFoundError):
        service.submit("no.such.tool", {})


def test_submit_get_cancel_flow(service):
    result = service.submit(TEST_TOOL_ID, {"segments": ["a", "b"]})
    assert result["status"] == "queued"

    task = service.get(result["handle"])
    assert task["tool_id"] == TEST_TOOL_ID
    assert task["input"] == {"segments": ["a", "b"]}

    assert service.list(limit=10) != []

    cancelled = service.cancel(result["handle"])
    assert cancelled["status"] == "cancelled"

    with pytest.raises(TaskConflictError):
        service.cancel(result["handle"])
    with pytest.raises(TaskNotFoundError):
        service.get("t_nothere")
