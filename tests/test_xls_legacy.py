"""老版 .xls（OLE2）支持（U 批次）：值级转换 → 表格翻译流全链可用。

覆盖：is_xls 魔数双判 / xls→xlsx 值迁移（文本、整值浮点、日期、标题清洗）/
（合并单元格不迁移——xlrd 2.x 已不提供 merged_cells） extract_values 内部回退 / backfill_dict sheets 版式产物为 _中文.xlsx /
损坏文件抛 ToolPauseError（与 .doc 老格式同口径：暂停留档，不重试）。
夹具用 xlwt 现场生成，不留二进制文件。
"""
from __future__ import annotations

import importlib.util
import datetime as _dt
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_tool(rel: str):
    """按路径加载工具模块（私有名，避免污染 sys.modules 的包结构）。"""
    path = ROOT / rel / "main.py"
    spec = importlib.util.spec_from_file_location("_xls_test_" + rel.replace("/", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    return SimpleNamespace(handle="xls-handle", keys={})


def _make_xls(path: Path) -> Path:
    """xlwt 现场生成老版 .xls：两个 sheet，含表头/数字/日期/合并单元格。"""
    import xlwt

    book = xlwt.Workbook()
    q = book.add_sheet("Quotation")
    q.write(0, 0, "Item")
    q.write(0, 1, "Amount")
    q.write(0, 2, "Date")
    q.write(1, 0, "Installation service")
    q.write(1, 1, 12345.0)
    date_style = xlwt.XFStyle()
    date_style.num_format_str = "YYYY-MM-DD"
    q.write(1, 2, _dt.datetime(2024, 3, 15), date_style)
    q.write(2, 0, "Maintenance")

    note = book.add_sheet("Note条款")
    note.write(0, 0, "Payment terms")
    note.write(0, 1, "within 30 days")
    book.save(str(path))
    return path


def test_is_xls_magic_and_extension(tmp_path):
    from command_shared.xls_convert import OLE2_MAGIC, is_xls

    xls = _make_xls(tmp_path / "Bill of Quantity.xls")
    assert xls.read_bytes()[:8] == OLE2_MAGIC
    assert is_xls(xls)
    # 扩展名不符 / 魔数不符 → 不认
    xlsx = tmp_path / "a.xlsx"
    xlsx.write_bytes(xls.read_bytes())
    assert not is_xls(xlsx)
    fake = tmp_path / "b.xls"
    fake.write_bytes(b"PK\x03\x04rest")
    assert not is_xls(fake)


def test_xls_to_xlsx_values(tmp_path):
    from openpyxl import load_workbook

    from command_shared.xls_convert import xls_to_xlsx

    xls = _make_xls(tmp_path / "bill.xls")
    conv = xls_to_xlsx(xls)
    try:
        wb = load_workbook(conv, data_only=True)
        assert wb.sheetnames == ["Quotation", "Note条款"]
        q = wb["Quotation"]
        assert q.cell(1, 1).value == "Item"
        assert q.cell(2, 2).value == 12345  # 整值浮点写回 int
        assert q.cell(2, 3).value == _dt.datetime(2024, 3, 15)  # 日期还原
        assert q.cell(3, 1).value == "Maintenance"
    finally:
        conv.unlink(missing_ok=True)


def test_extract_values_falls_back_for_xls(ctx, tmp_path):
    extract = load_tool("tools/xlsx/extract_values")
    xls = _make_xls(tmp_path / "Part 3.6 - Bill of Quantity.xls")
    out = extract.run({"file": str(xls)}, ctx, lambda e: None)

    assert out["kind"] == "xlsx"
    assert out["file"].endswith(".xls")  # 对外仍报原文件（run 身份不变）
    by_id = {u["unit_id"]: u for u in out["units"]}
    assert set(by_id) == {"Quotation", "Note条款"}
    rows = by_id["Quotation"]["rows"]
    assert rows[0] == ["Item", "Amount", "Date"]
    assert rows[1][0] == "Installation service"
    assert rows[1][1] == "12345"  # _format_cell 整值口径
    assert rows[1][2].startswith("2024-03-15")


def test_backfill_sheets_for_xls_produces_xlsx(ctx, tmp_path):
    """端到端：老版 .xls → 产物 <原名>_中文.xlsx，布局与 E1 完全一致。"""
    from openpyxl import load_workbook

    classify = load_tool("tools/table/classify_columns")
    dedup_mod = load_tool("tools/text/dedup_values")
    backfill = load_tool("tools/xlsx/backfill_dict")

    xls = _make_xls(tmp_path / "Part 3.6 - Bill of Quantity.xls")
    units = load_tool("tools/xlsx/extract_values").run({"file": str(xls)}, ctx, lambda e: None)["units"]
    cls = classify.run({"units": units}, None, lambda e: None)
    dedup = dedup_mod.run({"segments": cls["segments"]}, None, lambda e: None)
    n = len(dedup["unique"])
    out = backfill.run(
        {"units": units, "col_classes": cls["col_classes"], "ranges": cls["ranges"],
         "segments": cls["segments"], "index_map": dedup["index_map"],
         "date_maps": dedup["date_maps"],
         "translations": [f"译{i}" for i in range(n)],
         "statuses": ["ok"] * n, "file": str(xls)},
        ctx, lambda e: None,
    )

    assert out["layout"] == "sheets"
    assert out["name"] == "Part 3.6 - Bill of Quantity_中文.xlsx"  # 产物天然 .xlsx
    wb = load_workbook(out["path"])
    assert wb.sheetnames == ["Quotation", "Quotation_翻译结果",
                             "Note条款", "Note条款_翻译结果"]
    # 译文回填 + 原 sheet 值保留
    idx = {s: i for i, s in enumerate(dedup["unique"])}
    assert wb["Quotation_翻译结果"].cell(1, 1).value == f"译{idx['Item']}"
    assert wb["Quotation"].cell(1, 1).value == "Item"


def test_corrupted_xls_pauses(ctx, tmp_path):
    """损坏/加密的 .xls：抛 ToolPauseError（提示替换原件），不重试不失败。"""
    from command_shared.xls_convert import is_xls, xls_to_xlsx
    from core.errors import ToolPauseError

    bad = tmp_path / "broken.xls"
    bad.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"garbage" * 32)
    assert is_xls(bad)
    with pytest.raises(ToolPauseError) as ei:
        xls_to_xlsx(bad)
    assert "替换原件" in str(ei.value)


def test_safe_title_sanitizes_and_dedupes():
    from command_shared.xls_convert import _safe_title

    used: set[str] = set()
    # openpyxl 非法字符（:\/*?[]）替换为 _，且同名去重
    assert _safe_title("Note:条款?", used) == "Note_条款_"
    used.add("Note_条款_")
    assert _safe_title("Note:条款?", used) == "Note_条款__2"
    # 空名兜底
    assert _safe_title("  ", set()) == "Sheet"
