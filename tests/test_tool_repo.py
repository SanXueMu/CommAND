"""tool_repo 集成测试：打 dev 库（command_dev @ 41 pglab），不可达自动跳过。"""

import os

import pytest

from core.protocol import ToolManifest
from store.db import Db
from store.tool_repo import ToolRepo

DB_URL = os.environ.get("DATABASE_URL", "postgresql://command:root@192.168.8.41:5432/command_dev")


def _db_reachable() -> bool:
    try:
        return Db(DB_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture
def repo():
    db = Db(DB_URL)
    db.apply_migrations()
    yield ToolRepo(db)
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM tools WHERE id = 'text.llm.translate'")


def test_upsert_idempotent_and_roundtrip(repo, sample_manifest_toml):
    manifest = ToolManifest.from_toml(sample_manifest_toml)
    repo.upsert(manifest)
    repo.upsert(manifest)

    tools = repo.list_active()
    assert any(t["id"] == "text.llm.translate" for t in tools)

    one = repo.get("text.llm.translate")
    assert one is not None
    assert one["manifest"]["runtime"]["kind"] == "inproc"
    assert one["manifest"]["resources"]["max_attempts"] == 3


def test_get_missing_returns_none(repo):
    assert repo.get("no.such.tool") is None
