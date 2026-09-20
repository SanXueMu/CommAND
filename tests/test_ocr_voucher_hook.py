"""凭证页级钩子（VOUCHER_POSTPROCESS_CODE）行为锁定。

2026-09-20 用户口径：
1) 「合计大写」列只存识别原文——纸面空缺时保持空串，不做程序换算回填（砍兜底②）；
2) 借贷不平衡（真问题）与大写与金额不符（多为模型误推大写）分开报，避免误伤；
3) 大写不符时在备注里给「标准大写」供人工核对原件，但绝不写进大写列。
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


def test_mismatch_clears_fabricated_upper_and_notes_standard(hook):
    """借=贷但大写不符（模型编造）：清空大写列，原件值与标准大写进备注；备注须简短。"""
    out, logs = _run(hook, [_row(borrow="15949.00", credit="15949.00",
                                 dx="壹佰伍拾玖万肆仟玖佰元整")])
    assert out[0]["合计大写"] == "", "与借贷合计不符的大写（模型编造）必须清空"
    note = out[0]["备注"]
    assert note == "大写不符：原件「壹佰伍拾玖万肆仟玖佰元整」应为「壹万伍仟玖佰肆拾玖元整」"
    assert len(note) <= 40, f"备注须简短（现 {len(note)} 字）: {note}"
    assert logs and logs[0] == note, "日志与备注同源"


def test_conflict_rows_also_cleared(hook):
    """同行大写互相不一致（疑串行）：一并清空，备注给标准大写（不罗列原件值）。"""
    out, _ = _run(hook, [
        _row(borrow="100.00", dx="壹佰元整"),
        _row(credit="100.00", dx="贰佰元整"),
    ])
    assert {r["合计大写"] for r in out} == {""}
    assert out[0]["备注"] == "大写各行不一致，应为「壹佰元整」"


def test_imbalance_reports_borrow_credit(hook):
    """真借贷不平：报「借贷不平」，不混入大写口径。"""
    out, _ = _run(hook, [_row(borrow="100.00"), _row(credit="200.00")])
    assert "借贷不平" in out[0]["备注"] and "100.00" in out[0]["备注"] and "200.00" in out[0]["备注"]


def test_empty_upper_not_backfilled(hook):
    """纸面大写栏空缺：保持空串，不做程序回填（砍兜底②）。"""
    out, logs = _run(hook, [_row(borrow="968.00", credit="968.00", dx="")])
    assert out[0]["合计大写"] == "", "空缺大写不得被程序换算值填充"
    assert out[0]["备注"] == "" and not logs


def test_digit_form_upper_cleared(hook):
    """大写栏混入阿拉伯数字/￥：视为误抄清空（兜底①保留），且不影响借贷平衡判定。"""
    out, logs = _run(hook, [_row(borrow="511.84", credit="511.84", dx="51184")])
    assert out[0]["合计大写"] == ""
    assert out[0]["备注"] == "" and not logs, "数字形态解析后与借贷一致 → 不报不平"


def test_correct_upper_untouched(hook):
    """识别正确且与借贷合计一致的中文大写：原样保留、无备注。"""
    out, logs = _run(hook, [_row(borrow="511.84", credit="511.84", dx="伍佰壹拾壹元捌角肆分")])
    assert out[0]["合计大写"] == "伍佰壹拾壹元捌角肆分"
    assert out[0]["备注"] == "" and not logs


def test_imbalance_keeps_upper(hook):
    """借贷本身不平：金额不可信 → 不动大写列（只报借贷不平），留待人工核对。"""
    out, _ = _run(hook, [_row(borrow="100.00"), _row(credit="200.00", dx="壹佰元整")])
    assert any(r["合计大写"] == "壹佰元整" for r in out), "借贷不平时不得据此清空大写"
    assert "借贷不平" in out[0]["备注"]


def test_upper_never_becomes_digits(hook):
    """大写列永不出数字：各种输入下都不允许被换算成阿拉伯数字。"""
    for dx in ["壹仟元整", "叁仟元正", "51184", "伍佰壹拾壹元捌角肆分"]:
        out, _ = _run(hook, [_row(borrow="1000.00", credit="1000.00", dx=dx)])
        value = out[0]["合计大写"]
        assert value == "" or not any(ch.isdigit() for ch in value), f"大写列出现数字：{value!r}"
