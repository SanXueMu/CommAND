"""老版 .xls（OLE2 二进制）→ .xlsx 转换：值级迁移（xlrd 读、openpyxl 写）。

背景：openpyxl 不支持 2003 二进制格式；声明层把 .xls 与 .xlsx 同路由到表格翻译流，
故在工具内部先把 .xls 转成 .xlsx 再走原链路（提取/回填共用，保证 sheet 命名一致）。
迁移范围：全部 sheet、单元格值（文本/数字/日期/布尔/错误码）。样式与合并单元格
不迁移（xlrd 2.x 已不提供 merged_cells；翻译按值进行，不受影响）。

打不开 / 加密 / 损坏的 .xls 抛 ToolPauseError（提示用 Excel 另存为 .xlsx 后「替换原件」），
与 .doc 老格式同一口径：不重试、留档可人工处理。
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

#: OLE2 复合文档魔数（.doc/.xls/.msi 等老 Office 格式共用）
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_BAD_TITLE = re.compile(r"[\\/*?:\[\]]")


def is_xls(path: Path) -> bool:
    """按「扩展名 + OLE2 魔数」双判：只认真正的老版 .xls，不误伤改名的文件。"""
    try:
        if path.suffix.lower() != ".xls":
            return False
        with open(path, "rb") as f:
            return f.read(8) == OLE2_MAGIC
    except OSError:
        return False


def _safe_title(name: str, used: set[str]) -> str:
    """xlrd sheet 名 → openpyxl 合法且唯一的标题（≤31 字符）。"""
    title = (_BAD_TITLE.sub("_", name).strip() or "Sheet")[:31]
    base, n = title, 2
    while title in used:
        suffix = f"_{n}"
        title = base[: 31 - len(suffix)] + suffix
        n += 1
    return title


def xls_to_xlsx(src: Path) -> Path:
    """.xls → 临时 .xlsx（调用方负责删除临时文件）。"""
    import xlrd
    from openpyxl import Workbook

    from core.errors import ToolPauseError

    try:
        book = xlrd.open_workbook(str(src), on_demand=False)
    except Exception as exc:  # xlrd.XLRDError / struct.error / 加密 / 非 xls 的 OLE2
        raise ToolPauseError(
            f"老版 .xls 无法读取（{exc}）：请用 Excel 另存为 .xlsx 后，"
            "在任务清单用「替换原件」重新提交") from exc
    try:
        from xlrd.biffh import error_text_from_code
        from xlrd.xldate import xldate_as_datetime

        wb = Workbook()
        wb.remove(wb.active)
        titles: dict[str, str] = {}
        used: set[str] = set()
        for sheet in book.sheets():
            title = _safe_title(sheet.name, used)
            used.add(title)
            titles[sheet.name] = title
            ws = wb.create_sheet(title=title)
            for r in range(sheet.nrows):
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    value = None
                    if cell.ctype == xlrd.XL_CELL_TEXT:
                        value = cell.value
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        f = float(cell.value)
                        # 整值浮点写回 int，与提取侧「1 而非 1.0」的口径一致
                        value = int(f) if f.is_integer() and abs(f) < 1e15 else f
                    elif cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xldate_as_datetime(cell.value, book.datemode)
                        except (ValueError, OverflowError):
                            value = cell.value
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value = bool(cell.value)
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        value = error_text_from_code.get(cell.value, f"#ERR({cell.value})")
                    # XL_CELL_EMPTY / XL_CELL_BLANK → None
                    ws.cell(row=r + 1, column=c + 1).value = value
        fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="xlsconv_")
        os.close(fd)
        wb.save(tmp)
        return Path(tmp)
    finally:
        try:
            book.release_resources()
        except Exception:
            pass
