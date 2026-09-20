"""凭证页级钩子（VOUCHER_POSTPROCESS_CODE）行为锁定。

2026-09-20 用户口径（最终）：
1) 「合计大写」= **模型识别原文**（含数字/￥视为误抄清空），不做程序回填；
2) 「标准大写」= 按借贷合计生成（借贷一致时；不平则留空）——两列并排供人工对照；
3) 备注一条、简短且**写明前提条件**：借≠贷 / 大写为空（分两种成因）/ 大写与金额不符；
   大写比较按**数值**（「…元正」与「…元整」同值不算不符）。
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


def _row(borrow: str = "", credit: str = "", dx: str = "", subject: str = "管理费用") -> dict:
    return {"日期": "2002年5月8日", "凭证类别": "付", "凭证号": "总1号", "摘要": "报刊费",
            "总账科目": subject, "明细科目": "", "借方金额": borrow, "贷方金额": credit,
            "附件": "1张", "领款人": "王记", "合计大写": dx, "备注": ""}


def _run(hook, rows):
    logs: list[str] = []
    out = hook([dict(r) for r in rows], {"review": logs.append})
    return out, logs


def test_consistent_value_no_note(hook):
    """大写与金额同值：无备注（「元正」与「元整」同值不算不符）。"""
    out, logs = _run(hook, [_row(borrow="5440.00", credit="5440.00", dx="伍仟肆佰肆拾元正")])
    assert out[0]["合计大写"] == "伍仟肆佰肆拾元正"
    assert out[0]["标准大写"] == "伍仟肆佰肆拾元整"
    assert out[0]["备注"] == "" and not logs


def test_mismatch_notes_precondition(hook):
    """借=贷 但大写与金额不符：备注写明前提（原件 vs 应为），两列仍并排。"""
    out, logs = _run(hook, [_row(borrow="1000.00", credit="1000.00", dx="壹拾万元整")])
    assert out[0]["备注"] == "大写不符：原件「壹拾万元整」应为「壹仟元整」"
    assert out[0]["合计大写"] == "壹拾万元整" and out[0]["标准大写"] == "壹仟元整"
    assert logs and logs[0] == out[0]["备注"], "日志与备注同源"


def test_blank_upper_notes_blank_or_missed(hook):
    """纸面大写栏空白/未识别：备注写明无法确认，标准大写列给出按金额生成的值。"""
    out, _ = _run(hook, [_row(borrow="968.00", credit="968.00", dx="")])
    assert out[0]["备注"] == "大写无法确认：纸面空白或未识别"
    assert out[0]["合计大写"] == "" and out[0]["标准大写"] == "玖佰陆拾捌元整"


def test_digit_upper_cleared_and_notes_miscopy(hook):
    """模型照抄金额数字格：清空并写明「原文含数字已清空」（区别于纸面空白）。"""
    out, _ = _run(hook, [_row(borrow="511.84", credit="511.84", dx="51184")])
    assert out[0]["合计大写"] == ""
    assert out[0]["备注"] == "大写无法确认：原文含数字已清空"
    assert out[0]["标准大写"] == "伍佰壹拾壹元捌角肆分"


def test_imbalance_notes_and_blanks_standard(hook):
    """真借贷不平：备注简短；标准大写留空（金额不可信）；不动原件大写。"""
    out, logs = _run(hook, [_row(borrow="100.00"), _row(credit="200.00", dx="壹佰元整")])
    assert out[0]["备注"] == "借贷不平：借 100.00，贷 200.00"
    assert out[0]["标准大写"] == "", "借贷不平时不得给出标准大写"
    assert any(r["合计大写"] == "壹佰元整" for r in out), "借贷不平时不得据此清空大写"
    assert logs and logs[0] == out[0]["备注"]


def test_imbalance_with_blank_upper_appends_unconfirmable(hook):
    """借贷不平且大写为空：备注在「借贷不平」后补一句「大写无法确认」。"""
    out, _ = _run(hook, [_row(borrow="100.00"), _row(credit="200.00", dx="")])
    assert out[0]["备注"] == "借贷不平：借 100.00，贷 200.00；大写无法确认"


def test_summary_page_keeps_source_totals(hook):
    """科目汇总表页（含「合计」行）：借贷不平备注附源表合计数。"""
    out, _ = _run(hook, [
        _row(borrow="100.00", dx="壹佰元整"), _row(credit="150.00", dx="壹佰元整"),
        _row(borrow="100.00", credit="150.00", dx="壹佰元整", subject="合计"),
    ])
    assert out[0]["备注"] == "借贷不平：借 100.00，贷 150.00（源表 100.00/150.00）"


def test_upper_never_becomes_digits(hook):
    """「合计大写」列永不出数字：各种输入下都不允许被换算成阿拉伯数字。"""
    for dx in ["壹仟元整", "叁仟元正", "51184", "伍佰壹拾壹元捌角肆分"]:
        out, _ = _run(hook, [_row(borrow="1000.00", credit="1000.00", dx=dx)])
        value = out[0]["合计大写"]
        assert value == "" or not any(ch.isdigit() for ch in value), f"大写列出现数字：{value!r}"
