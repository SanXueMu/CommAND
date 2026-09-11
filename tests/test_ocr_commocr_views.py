"""CommOCR 用户视图移植校验：6 个已进声明预设，ViewSpec 可编译、空跑不崩。"""

from command_shared.ocr_views import ViewSpec, compute_view
from store.site_views.ocr import OCR_VIEW
from store.site_views.ocr_user_views import COMMOCR_USER_VIEWS

EXPECTED_IDS = {
    "user.blueprint.info",
    "user.blueprint.table",
    "user.english.docs",
    "user.contract.table",
    "user.risk.list",
    "user.contract.keywords",
}


def _presets() -> list[dict]:
    return OCR_VIEW["props"]["builtinViews"]


def test_user_views_count_and_ids():
    assert len(COMMOCR_USER_VIEWS) == 6
    assert {v["id"] for v in COMMOCR_USER_VIEWS} == EXPECTED_IDS
    for v in COMMOCR_USER_VIEWS:
        assert v["source_id"] and v["name"] and v["spec"]


def test_declaration_merges_builtin_and_user():
    presets = _presets()
    assert len(presets) == 11  # 5 内置 + 6 用户
    names = [p["name"] for p in presets]
    for expected in ("平面图信息清单", "平面图表格明细", "英文单据还原视图",
                     "09合同表格明细（双Sheet）", "风险提示清单", "02合同关键词视图"):
        assert expected in names


def test_all_presets_compile_and_dry_run():
    for p in _presets():
        spec = ViewSpec(**p["spec"])
        out = compute_view([], spec)
        assert isinstance(out, dict)
