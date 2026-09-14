"""协议 v2 站点清单（蓝图 03）：内置声明结构与 /meta/site 端点一致性（PG 装配版）。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from store.site_seed import BUILTIN_SITE_VIEWS


def test_builtin_site_views_shape() -> None:
    ids = [v["id"] for v in BUILTIN_SITE_VIEWS]
    assert len(ids) == len(set(ids)), "视图 id 不得重复"
    assert sum(1 for v in BUILTIN_SITE_VIEWS if v.get("default")) <= 1, "default 视图至多一个"
    for view in BUILTIN_SITE_VIEWS:
        assert view["id"] and view["type"] and view["title"]
        if "when" in view:
            assert set(view["when"]) == {"capability"}, "when 仅支持 capability 条件"


def test_builtin_includes_protocol_and_manager_views() -> None:
    ids = set(ids for ids in (v["id"] for v in BUILTIN_SITE_VIEWS))
    assert {"tools", "flows", "tasks", "work", "settings"} <= ids, "协议级通用视图必须在内置声明中"
    assert "templates" in ids, "模版管理视图必须在内置声明中"
    # 裁定五（乱归 Tab）：OCR 子功能按三级概念归流库，不得再占导航 Tab
    assert not ({"ocr-recognize", "ocr-results", "ocr-views", "ocr-specgen"} & ids), \
        "OCR 专属视图已按三级概念退场，不允许回归内置声明"


def test_builtin_nav_model_is_coherent() -> None:
    """props.nav（页眉渲染模型）：kind 合法、子项必有父、菜单父项必须存在、header 项带标签。

    导航结构现在是声明驱动的（CommWEB 只按 kind 渲染），所以拼错一个 group 名
    或漏掉父项都会让整条视图在页眉里凭空消失——此测试即该形状的静态防线。
    """
    by_id = {v["id"]: v for v in BUILTIN_SITE_VIEWS}
    kinds: dict[str, str] = {}
    for view in BUILTIN_SITE_VIEWS:
        nav = (view.get("props") or {}).get("nav") or {}
        kind = nav.get("kind", "tab")
        assert kind in {"tab", "menu", "child", "header", "hidden"}, f"{view['id']} 的 nav.kind 非法: {kind}"
        kinds[view["id"]] = kind
        if kind == "child":
            group = nav.get("group")
            assert group, f"{view['id']} 为 child 但未声明 group"
            assert by_id.get(group), f"{view['id']} 的 group={group} 不存在"
            assert nav.get("label"), f"{view['id']} 为 child 但未声明 label（下拉文案）"
        if kind == "header":
            assert nav.get("label"), f"{view['id']} 为 header 但未声明 label"
        if kind == "menu":
            assert "defaultLabel" in (view.get("props") or {}), f"{view['id']} 为 menu 但未声明 defaultLabel"

    menus = {vid for vid, k in kinds.items() if k == "menu"}
    # menu 的 defaultLabel 用于下拉首项（自身）文案；child 的 group 必须指向 menu
    for vid, kind in kinds.items():
        if kind == "child":
            group = by_id[vid]["props"]["nav"]["group"]
            assert group in menus, f"{vid} 的 group={group} 不是 menu 项"

    # 页眉「设置」下拉 + 工作区下拉的既定归属（改声明需同步改此断言）
    assert kinds["work"] == "menu" and kinds["ocr"] == "child" and kinds["translate"] == "child"
    assert by_id["ocr"]["props"]["nav"]["group"] == "work"
    assert by_id["translate"]["props"]["nav"]["group"] == "work"
    assert kinds["templates"] == "hidden", "模版管理改为弹窗面板，不得再占导航"
    assert kinds["settings"] == "header" and by_id["settings"]["props"]["nav"]["label"] == "APIKey管理"
    assert kinds["tools"] == "tab" and kinds["flows"] == "tab" and kinds["tasks"] == "tab"


def test_ocr_view_declares_full_builtin_specs() -> None:
    """内置视图以「名 → 完整 ViewSpec」下发：spec 须能直接过 ViewSpec 校验。

    回归防线：此前只下发视图名字符串，records.view.query 侧 ViewSpec(**str) 必抛
    TypeError，内置视图全线跑不通；现将零引用的 ocr_views.BUILTIN_VIEWS 接进声明。
    """
    from command_shared.ocr_views import ViewSpec

    ocr = next(v for v in BUILTIN_SITE_VIEWS if v["id"] == "ocr")
    views = ocr["props"]["builtinViews"]
    assert views and all(isinstance(v, dict) for v in views)
    for item in views:
        assert item["id"] and item["name"]
        spec = ViewSpec(**item["spec"])
        assert spec.name == item["name"], "name 须取自 spec.name，保持与工具侧一致"
    assert {v["name"] for v in views} >= {
        "发票凭证视图", "合同清单视图", "审批签单视图", "合同关键词视图", "决算审定表视图",
    }


def test_meta_site_serves_from_repo(monkeypatch) -> None:
    """端点从 repo 装配：假 repo 返回 seed 声明 → /meta/site 原样下发。"""

    class FakeRepo:
        def list(self):
            return [
                {
                    "id": "tools", "type": "tools.grid", "title": "工具库", "icon": "appstore-outlined",
                    "when": None, "props": {"defaultLayout": "card"}, "sort": 10, "default": True,
                },
                {
                    "id": "ocr-views", "type": "data.browser", "title": "OCR 视图导出", "icon": None,
                    "when": {"capability": "has_files"}, "props": {"source": {"kind": "records_json"}}, "sort": 120, "default": False,
                },
            ]

    import deps
    from api import meta_router

    monkeypatch.setattr(deps, "get_site_repo", lambda: FakeRepo())
    app = FastAPI()
    app.include_router(meta_router.router, prefix="/api")
    client = TestClient(app)
    body = client.get("/api/meta/site").json()["site"]
    assert body["protocolVersion"] == "2"
    assert [v["id"] for v in body["views"]] == ["tools", "ocr-views"]
    assert "when" not in body["views"][0], "when 为 None 时不得下发空键"
    assert body["views"][1]["when"] == {"capability": "has_files"}
