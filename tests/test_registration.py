"""注册表接口测试（蓝图「飞升」§快速启动）：

模板自洽环：build_template → 填行 → parse_workbook → validate → migration → apply（写 site_views 后恢复现场）。
校验规则与 CommWEB src/protocol/registration.test.ts 同语义（跨端对账）。
"""

from __future__ import annotations

import secrets

import pytest

from services.registration_service import (
    RegistrationService,
    build_template,
    parse_workbook,
    to_migration,
    validate_rows,
)
from store.db import Db
from store.site_repo import SiteRepo
from tests._dbutil import db_reachable

DB_URL = "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
pytestmark = pytest.mark.skipif(not db_reachable(DB_URL), reason="dev PG 不可达，跳过集成测试")


@pytest.fixture()
def svc() -> RegistrationService:
    db = Db(DB_URL)
    db.apply_migrations()
    return RegistrationService(site_repo=SiteRepo(db), db=db)


def _rows(over: list[dict]) -> list[dict]:
    base = {"id": "t-home", "type": "workspace.tabs", "title": "首页", "icon": None,
            "navKind": None, "navGroup": None, "navOrder": None,
            "default": None, "sort": None, "whenCapability": None, "propsJson": None}
    return [{**base, **r} for r in over]


def test_template_self_consistent_roundtrip():
    data = build_template()
    rows = parse_workbook(data)
    assert len(rows) == 3  # 三个示例行
    errors, _ = validate_rows(rows)
    assert errors == []
    migration = to_migration(rows)
    assert migration["kind"] == "registration"
    assert migration["version"] == 1
    by_id = {v["id"]: v for v in migration["views"]}
    assert by_id["work"]["props"]["nav"]["kind"] == "menu"
    assert by_id["work-tasks"]["props"]["nav"] == {"kind": "child", "group": "work"}
    assert by_id["keys"]["props"]["nav"] == {"kind": "header", "order": 5}
    assert by_id["keys"]["when"] == {"capability": "has_pipelines"}


def test_validate_rules_mirror_commweb():
    errors, warnings = validate_rows(_rows([
        {"id": "", "title": "x"},
        {"id": "Bad_Id", "title": "x"},
        {"id": "dup", "title": "a"},
        {"id": "dup", "title": "b"},
        {"id": "u1", "type": "nope.view", "title": "x"},
        {"id": "c1", "navKind": "child"},
        {"id": "c2", "navKind": "child", "navGroup": "ghost"},
        {"id": "w1", "icon": "star-outlined", "title": "x"},
    ]))
    assert any("id 必填" in e for e in errors)
    assert any("id 须为" in e for e in errors)
    assert any("id 重复" in e for e in errors)
    assert any("未知视图类型" in e for e in errors)
    assert any("必须填 navGroup" in e for e in errors)
    assert any("没有对应声明行" in e for e in errors)
    assert any("回落默认图标" in w for w in warnings)


def test_to_migration_rejects_invalid():
    with pytest.raises(ValueError, match="校验未通过"):
        to_migration(_rows([{"id": "u1", "type": "nope.view"}]))


def test_preview_and_apply_roundtrip(svc: RegistrationService):
    marker = secrets.token_hex(3)
    rows = _rows([
        {"id": f"reg-{marker}", "type": "tasks.table", "title": "注册测试", "navKind": "menu",
         "icon": "unordered-list-outlined"},
        {"id": f"reg-{marker}-child", "type": "data.browser", "title": "注册子项",
         "navKind": "child", "navGroup": f"reg-{marker}"},
    ])
    migration = to_migration(rows)
    try:
        result = svc.apply(migration)
        assert f"reg-{marker}" in result["applied"]
        assert f"reg-{marker}-child" in result["applied"]
        listed = {v["id"]: v for v in svc._site_repo.list()}
        assert listed[f"reg-{marker}"]["type"] == "tasks.table"
        assert listed[f"reg-{marker}-child"]["props"]["nav"] == {"kind": "child", "group": f"reg-{marker}"}
    finally:
        svc._site_repo.delete(f"reg-{marker}")
        svc._site_repo.delete(f"reg-{marker}-child")


def test_apply_rejects_client_tampering(svc: RegistrationService):
    migration = {"version": 1, "kind": "registration", "views": [
        {"id": "bad_VIEW", "type": "tasks.table", "title": "x", "props": {}}]}
    with pytest.raises(ValueError, match="校验未通过"):
        svc.apply(migration)
    with pytest.raises(ValueError, match="仅支持"):
        svc.apply({"version": 2, "kind": "registration", "views": []})
