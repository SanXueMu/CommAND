"""scheduler 端到端集成测试：真库 + 真工具目录 + run_once 同步驱动。"""

import os
import threading
from pathlib import Path

import pytest

from config import load_config
from core.runner import Runner
from core.scheduler import Scheduler
from store.db import Db
from store.event_repo import EventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo
from tests.test_task_repo import TEST_TOOL_ID, _manifest  # 复用测试 manifest 工厂

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_URL = os.environ.get("DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev")

DEV_REVERSE_ID = "dev.string.reverse"


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def scheduler():
    db = Db(DB_URL)
    db.apply_migrations()
    tool_repo = ToolRepo(db)
    task_repo = TaskRepo(db)
    from core.protocol import ToolManifest
    reverse_manifest = ToolManifest.from_toml(REPO_ROOT / "tools" / "dev" / "string_reverse" / "tool.toml")
    tool_repo.upsert(reverse_manifest, path="tools/dev/string_reverse")
    config = load_config(".env")
    sched = Scheduler(
        db=db,
        runner=Runner(),
        task_repo=task_repo,
        tool_repo=tool_repo,
        event_repo=EventRepo(db),
        config=config,
    )
    yield sched
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tasks WHERE tool_id IN (%s, %s)", (DEV_REVERSE_ID, TEST_TOOL_ID))
        conn.execute("DELETE FROM tools WHERE id IN (%s, %s)", (DEV_REVERSE_ID, TEST_TOOL_ID))
    db.close()


def test_e2e_subprocess_task_succeeds(scheduler):
    repo = scheduler._task_repo  # noqa: SLF001 — 测试直达仓储
    event_repo = scheduler._event_repo  # noqa: SLF001
    handle = repo.enqueue(DEV_REVERSE_ID, {"segments": ["abc", "你好"]}, max_attempts=1)

    assert scheduler.run_once("w-test") is True

    task = repo.get(handle)
    assert task["status"] == "succeeded"
    assert task["output"] == {"segments": ["cba", "好你"]}
    events = event_repo.list_by_handle(handle)
    assert events == [], "subprocess 参考工具不发事件，事件流应为空"


def test_e2e_domain_error_retries_then_failed_review(scheduler, tmp_path: Path):
    flaky_tool = tmp_path / "flaky"
    flaky_tool.mkdir()
    (flaky_tool / "main.py").write_text(
        "def run(input, ctx, emit):\n"
        "    from core.errors import ToolDomainError\n"
        "    raise ToolDomainError('限流')\n",
        encoding="utf-8",
    )
    manifest = _manifest(concurrency=1, max_attempts=2)
    scheduler._tool_repo.upsert(manifest, path=str(flaky_tool))  # noqa: SLF001
    repo = scheduler._task_repo  # noqa: SLF001

    handle = repo.enqueue(TEST_TOOL_ID, {}, max_attempts=2)
    assert scheduler.run_once("w-test") is True
    task = repo.get(handle)
    assert task["status"] == "queued" and task["attempt"] == 2, "领域错误应重试回队"

    assert scheduler.run_once("w-test") is True
    task = repo.get(handle)
    assert task["status"] == "failed_review"
    assert task["error"]["kind"] == "domain"


def test_e2e_cancel_running_task(scheduler, tmp_path: Path):
    slow_tool = tmp_path / "slow"
    slow_tool.mkdir()
    (slow_tool / "main.py").write_text(
        "import time\n"
        "def run(input, ctx, emit):\n"
        "    from core.errors import TaskCancelled\n"
        "    for _ in range(100):\n"
        "        if ctx.cancel_event.is_set():\n"
        "            raise TaskCancelled(ctx.handle)\n"
        "        time.sleep(0.1)\n"
        "    return {}\n",
        encoding="utf-8",
    )
    manifest = _manifest(concurrency=1, max_attempts=1)
    scheduler._tool_repo.upsert(manifest, path=str(slow_tool))  # noqa: SLF001
    repo = scheduler._task_repo  # noqa: SLF001

    handle = repo.enqueue(TEST_TOOL_ID, {}, max_attempts=1)
    worker = threading.Thread(target=scheduler.run_once, args=("w-test",), daemon=True)
    worker.start()

    deadline = threading.Event()
    import time
    for _ in range(50):
        if handle in scheduler._running:  # noqa: SLF001
            break
        time.sleep(0.1)
    assert scheduler.request_cancel(handle) is True
    worker.join(timeout=10)
    assert not worker.is_alive()

    task = repo.get(handle)
    assert task["status"] == "cancelled"
