"""协议控制面集成测试（蓝图「飞升」§会员映像与同步状态机）。

覆盖：发布幂等登记 / 采集去重 / 同步 SUCCEEDED + 投影翻转 / 幂等重放 /
INCOMPATIBLE（映像 schema 高于目标发布）+ 失败不动旧投影 / state 总览。
"""

from __future__ import annotations

import secrets

import pytest

from services.protocol_sync_service import (
    CURRENT_RELEASE_ID,
    CURRENT_SNAPSHOT_SCHEMA,
    ProtocolSyncService,
)
from store.db import Db
from store.protocol_repo import ProtocolRepo
from store.site_repo import SiteRepo
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture()
def svc() -> ProtocolSyncService:
    db = Db(DB_URL)
    db.apply_migrations()
    service = ProtocolSyncService(db=db, repo=ProtocolRepo(db), site_repo=SiteRepo(db))
    service.ensure_current_release()
    return service


def _mk_snapshot(repo: ProtocolRepo, provider_id: str, views: list[dict], schema_version: int = CURRENT_SNAPSHOT_SCHEMA):
    payload = {"name": "test", "views": views}
    import hashlib

    from store.protocol_repo import _canonical_json

    checksum = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()[:16]
    return repo.insert_snapshot(provider_id, CURRENT_RELEASE_ID, schema_version, payload, checksum)


def test_ensure_release_idempotent(svc: ProtocolSyncService):
    svc.ensure_current_release()
    svc.ensure_current_release()
    releases = svc._repo.list_releases()
    assert len([r for r in releases if r["id"] == CURRENT_RELEASE_ID]) == 1


def test_capture_default_and_dedupe(svc: ProtocolSyncService):
    """确定性去重验证：临时注入声明使内容必变 → 首采不重复；复采命中；恢复现场。"""
    repo_views = svc._site_repo
    marker = f"dedup-probe-{secrets.token_hex(4)}"
    repo_views.upsert({"id": marker, "type": "home", "title": "去重探针", "sort": 9999}, is_builtin=False)
    try:
        first = svc.capture("default")
        assert first["snapshot"]["id"] > 0
        assert first["deduped"] is False  # 内容刚变，必不重复
        second = svc.capture("default")
        assert second["deduped"] is True
        assert second["snapshot"]["id"] == first["snapshot"]["id"]
    finally:
        repo_views.delete(marker)
    third = svc.capture("default")
    assert third["deduped"] is False  # 删探针后内容又变，重新落行（探针行成为历史）


def test_sync_success_projection_and_replay(svc: ProtocolSyncService):
    repo = svc._repo
    pid = f"test-proto-{secrets.token_hex(4)}"
    snap_id = _mk_snapshot(repo, pid, [{"id": "home", "type": "home", "title": "首页"}])

    out = svc.sync(pid)
    assert out["run"]["status"] == "SUCCEEDED"
    assert out["run"]["snapshot_id"] == snap_id

    projection = repo.current_projection(pid)
    assert projection is not None
    assert projection["snapshot_id"] == snap_id
    assert projection["release_id"] == CURRENT_RELEASE_ID
    assert projection["payload"]["views"][0]["id"] == "home"

    replay = svc.sync(pid)
    assert replay["replayed"] is True
    assert replay["run"]["status"] == "SUCCEEDED"
    assert repo.current_projection(pid)["id"] == projection["id"]  # 未重复投影


def test_sync_incompatible_keeps_old_projection(svc: ProtocolSyncService):
    repo = svc._repo
    pid = f"test-proto-{secrets.token_hex(4)}"
    good_id = _mk_snapshot(repo, pid, [{"id": "a", "type": "home", "title": "A"}])
    assert svc.sync(pid)["run"]["status"] == "SUCCEEDED"
    before = repo.current_projection(pid)

    _mk_snapshot(repo, pid, [{"id": "b", "type": "home", "title": "B"}], schema_version=99)
    out = svc.sync(pid)
    assert out["run"]["status"] == "INCOMPATIBLE"
    assert "不支持降级" in out["run"]["error"] or "高于目标发布" in out["run"]["error"]

    after = repo.current_projection(pid)
    assert after["id"] == before["id"]  # 失败不动旧投影
    assert repo.succeeded_run(pid, good_id, CURRENT_RELEASE_ID) is not None


def test_sync_without_snapshot_raises(svc: ProtocolSyncService):
    pid = f"test-proto-{secrets.token_hex(4)}"
    with pytest.raises(ValueError, match="无会员映像"):
        svc.sync(pid)


def test_state_overview(svc: ProtocolSyncService):
    pid = f"test-proto-{secrets.token_hex(4)}"
    _mk_snapshot(svc._repo, pid, [{"id": "c", "type": "home", "title": "C"}])
    svc.sync(pid)
    state = svc.state(pid)
    assert state["provider_id"] == pid
    assert state["release"]["id"] == CURRENT_RELEASE_ID
    assert state["snapshot"]["payload"]["views"][0]["id"] == "c"
    assert state["projection"]["release_id"] == CURRENT_RELEASE_ID
    assert state["runs"][0]["status"] == "SUCCEEDED"
