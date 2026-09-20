"""凭证页级钩子（VOUCHER_POSTPROCESS_CODE）行为锁定。

2026-09-20 用户口径（最终）：
1) 「合计大写」= **模型识别原文**（含数字/￥视为误抄清空），不做程序回填；
2) 「标准大写」= 按借贷合计生成（借贷一致时；不平则留空）——两列并排供人工对照，
   用户无需从备注里粘贴；
3) 备注只留**借贷不平衡**（真问题）且保持简短；大写一致性不写备注。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "scripts" / "ocr_builtin_templates.py"


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("ocr_builtin_templates_test", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace: dict = {}
    exec(module.VOUCHER_POSTPROCESS_CODE, namespace)  # noqa: S102 - 测试钩子代码
    return namespace["transform_page"]


def _row(borrow: str = "", credit: str = "", dx: str = "") -> dict:
    return {"日期": "2002年5月8日", "凭证类别": "付", "凭证号": "总1号", "摘要": "报刊费",
            "总账科目": "管理费用", "明细科目": "", "借方金额": borrow, "贷方金额": credit,
            "附件": "1张", "领款人": "王记", "合计大写": dx, "备注": ""}


def _run(hook, rows):
    logs: list[str] = []
    out = hook([dict(r) for r in rows], {"review": logs.append})
    return out, logs


def test_mismatch_keeps_raw_and_fills_standard(hook):
    """借=贷但大写不符（模型编造）：原件值留在「合计大写」，标准大写进独立列，备注不写。"""
    out, logs = _run(hook, [_row(borrow="15949.00", credit="15949.00",
                                 dx="壹佰伍拾玖万肆仟玖佰元整")])
    assert out[0]["合计大写"] == "壹佰伍拾玖万肆仟玖佰元整", "模型原文须留在「合计大写」列"
    assert out[0]["标准大写"] == "壹万伍仟玖佰肆拾玖元整", "标准大写须进独立列供对照"
    assert out[0]["备注"] == "" and not logs, "大写不一致不再写备注（两列并排自明）"


def test_empty_upper_keeps_blank_but_standard_filled(hook):
    """纸面大写栏空缺：合计大写留空（不回填），标准大写列给出按金额生成的正确值。"""
    out, logs = _run(hook, [_row(borrow="968.00", credit="968.00", dx="")])
    assert out[0]["合计大写"] == "", "空缺大写不得被程序换算值填充"
    assert out[0]["标准大写"] == "玖佰陆拾捌元整"
    assert out[0]["备注"] == "" and not logs


def test_digit_form_upper_cleared_standard_kept(hook):
    """大写栏混入阿拉伯数字/￥：视为误抄清空（兜底①保留）；标准大写照给。"""
    out, logs = _run(hook, [_row(borrow="511.84", credit="511.84", dx="51184")])
    assert out[0]["合计大写"] == ""
    assert out[0]["标准大写"] == "伍佰壹拾壹元捌角肆分"
    assert out[0]["备注"] == "" and not logs


def test_correct_upper_kept_and_matches_standard(hook):
    """识别正确且与借贷合计一致：两列同值、无备注。"""
    out, logs = _run(hook, [_row(borrow="511.84", credit="511.84", dx="伍佰壹拾壹元捌角肆分")])
    assert out[0]["合计大写"] == "伍佰壹拾壹元捌角肆分"
    assert out[0]["标准大写"] == "伍佰壹拾壹元捌角肆分"
    assert out[0]["备注"] == "" and not logs


def test_imbalance_notes_short_and_standard_blank(hook):
    """真借贷不平：备注简短报「借贷不平」；标准大写留空（金额不可信）；不动原件大写。"""
    out, logs = _run(hook, [_row(borrow="100.00"), _row(credit="200.00", dx="壹佰元整")])
    note = out[0]["备注"]
    assert note == "借贷不平：借 100.00，贷 200.00", note
    assert out[0]["标准大写"] == "", "借贷不平时不得给出标准大写"
    assert any(r["合计大写"] == "壹佰元整" for r in out), "借贷不平时不得据此清空大写"
    assert logs and logs[0] == note, "日志与备注同源"


def test_upper_never_becomes_digits(hook):
    """「合计大写」列永不出数字：各种输入下都不允许被换算成阿拉伯数字。"""
    for dx in ["壹仟元整", "叁仟元正", "51184", "伍佰壹拾壹元捌角肆分"]:
        out, _ = _run(hook, [_row(borrow="1000.00", credit="1000.00", dx=dx)])
        value = out[0]["合计大写"]
        assert value == "" or not any(ch.isdigit() for ch in value), f"大写列出现数字：{value!r}"
