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


def test_builtin_voucher_view_record_mode_multi_row():
    """AG1：发票凭证内置视图 record 模式——一页多条分录必须逐条成行（不再页聚合折叠）。"""
    from command_shared.ocr_views import BUILTIN_VIEWS, compute_view
    spec = next(v for v in BUILTIN_VIEWS if v["id"] == "builtin-voucher")
    rows = [
        (3, {"月份": "2002-03", "凭证号": "记-5", "摘要": "购文具", "借方金额": "100.00"}),
        (3, {"月份": "2002-03", "凭证号": "记-5", "摘要": "现金", "贷方金额": "100.00"}),
        (4, {"月份": "2002-03", "凭证号": "记-6", "摘要": "付房租", "借方金额": "2000.00"}),
    ]
    result = compute_view(rows, type("S", (), {"__mro__": ()}) if False else _load_spec(spec["spec"]))
    assert len(result["rows"]) == 3
    assert result["rows"][0]["摘要"] == "购文具"
    assert result["rows"][1]["摘要"] == "现金"
    assert result["rows"][1]["页码"] == 3


def _load_spec(raw: dict):
    from command_shared.ocr_views import ViewSpec
    return ViewSpec(**raw)


def test_builtin_voucher_view_has_year_month_columns():
    """AO3/AM3：发票凭证视图含「年份」「月份」两列（first_value）与「标准大写」对照列。"""
    from command_shared.ocr_views import BUILTIN_VIEWS
    spec = next(v for v in BUILTIN_VIEWS if v["id"] == "builtin-voucher")["spec"]
    assert spec["columns"][:2] == ["年份", "月份"]
    agg = {a["column"]: a["op"] for a in spec["aggregates"]}
    assert agg["年份"] == "first_value" and agg["月份"] == "first_value"
    # 「合计大写」（模型原文）与「标准大写」（按借贷合计生成）并排，供人工对照
    assert agg["合计大写"] == "first_value" and agg["标准大写"] == "first_value"
    assert spec["columns"].index("标准大写") == spec["columns"].index("合计大写") + 1
