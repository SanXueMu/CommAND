"""commOcr 结果库 → 每来源一个 table 单元；长值独立 text 单元（translee extract_ocr_db 移植）。

records 表结构：source_path / page_number / data(JSON: 字段→值)。
短值进「字段 | 值」两列表格批翻；长值（> long_value_chars，如合同条款）
独立成 text 单元整篇翻译，unit_id 含来源/字段/页码。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager, closing
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def _file_hash_list(paths: list[Path]) -> str:
    """AJ1：多库合并导出的稳定哈希（排序后路径逐一哈希再汇总，与顺序无关）。"""
    inner = hashlib.sha256()
    for p in sorted(paths):
        inner.update(str(p).encode())
        inner.update(_file_hash(p).encode())
    return inner.hexdigest()


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _year_month_from_source(source_path: str) -> tuple[str, str, str]:
    """AO/AR：从原件文件名提取（年份, 首月, 尾月）三元组纯数字串。

    - 单月：2002年3月记账凭证_1_.pdf → ("2002", "3", "")
    - 区间：1993年9月-10月记账凭证.pdf → ("1993", "9", "10")；2001年4-12月 → ("2001", "4", "12")
    - 跨年：1993年11月-1994年1月 → 尾月按 +12 展开为 13（次年 1 月），便于区间比较
    拆两列是为 Excel 数值排序正确（「2002年10月」按文本序会排在「2002年2月」之前）。
    提不到时三元组皆空。
    """
    import re

    name = Path(source_path).name
    m = re.search(
        r"(\d{4})年\s*(\d{1,2})\s*月?\s*[-—~至到]\s*(?:\d{4}年\s*)?(\d{1,2})\s*月", name)
    if m:
        y, m1, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m2 < m1:
            m2 += 12  # 跨年区间：1993年11月-1994年1月 → 11..13
        return (str(y), str(m1), str(m2))
    m = re.search(r"(\d{4})年(\d{1,2})月", name)
    return (m.group(1), str(int(m.group(2))), "") if m else ("", "", "")


_DATE_PATTERNS = (
    r"(\d{4})\s*年\s*(\d{1,2})\s*月",   # 1993年10月5日 / 1993年10月
    r"(\d{4})[-/.](\d{1,2})",           # 1993-10-5 / 1993.10.5 / 1993/10/5
)


def _record_date_year_month(record: dict) -> tuple[str, str]:
    """AR：从记录自身日期字段解析（年份, 月份）原始数字串。

    区间文件名消歧用——凭证表头「日期」字段（01 模版字段名，兼容 date）。
    提不到时返回 ("", "")；只解析，不做区间判断（由调用方校验）。
    """
    import re

    raw = str(record.get("日期") or record.get("date") or "").strip()
    if not raw:
        return ("", "")
    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, raw)
        if m:
            return (m.group(1), str(int(m.group(2))))
    return ("", "")


def _year_month_key(record: dict) -> tuple[int, int]:
    """AO2：行序键——按（年份, 月份）数字序；无年月的记录排最后。

    AR：区间文件名下月份留空的行改用 _sk 回落键（区间首月）——
    空月份行仍与同文件聚组、保持页序，而不是被踢到全表末尾。
    """
    sk = record.get("_sk")
    if isinstance(sk, tuple):
        return sk
    year, month = str(record.get("年份") or ""), str(record.get("月份") or "")
    if year.isdigit() and month.isdigit():
        return (int(year), int(month))
    return (9999, 99)


def _ocr_storage_connection(p: Path):
    from command_shared import ocr_storage

    conn = ocr_storage.connect(p)
    ocr_storage.initialize(conn)
    return conn


def run(input: dict, ctx, emit) -> dict:
    # AJ1：file 接受单库或库列表（多库合并导出）；str 归一为单元素列表
    raw_files = input["file"]
    paths = [Path(p) for p in (raw_files if isinstance(raw_files, list) else [raw_files])]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {', '.join(missing)}")
    path = paths[0]  # 单库路径（units 模式/输出元信息沿用）
    long_value_chars = int(input.get("long_value_chars", 200))
    def _open(p: Path) -> AbstractContextManager:
        """统一走 ocr_storage 连接（触发旧库 seq 迁移），杜绝表结构知识散落。"""
        return closing(_ocr_storage_connection(p))

    mode = input.get("mode") or "units"

    if mode == "records":
        records: list[dict] = []
        # AJ1：多库逐读合并（页级缓存库间天然隔离，来源文件字段区分归属）；
        # AE 后同页多条分录按 seq 排序，跨库按来源路径分组有序
        for p in paths:
            with _open(p) as conn:
                cursor = conn.execute(
                    "SELECT source_path, page_number, data FROM records "
                    "ORDER BY source_path, page_number, seq"
                )
                for source_path, page_number, data_json in cursor:
                    try:
                        data = json.loads(data_json)
                    except (TypeError, json.JSONDecodeError):
                        data = {}
                    record = dict(data) if isinstance(data, dict) else {"数据": data}
                    record["页码"] = page_number
                    record["来源文件"] = Path(source_path).name
                    year, month, month_end = _year_month_from_source(source_path)
                    record["年份"] = year
                    if not month_end:
                        # 单月（或无名）文件名：现行为不变——文件名权威
                        record["月份"] = month
                    else:
                        # AR：区间文件名（如 1993年9月-10月）——月份由本条记录「日期」
                        # 限定消歧：解析出的绝对月份必须落在区间内才算数（防手写体
                        # OCR 误读，如 10 认成 1）；出界/解析失败留空，宁可空不可错
                        dy, dm = _record_date_year_month(record)
                        abs_m = None
                        if dy.isdigit() and dm.isdigit():
                            abs_m = (int(dy) - int(year)) * 12 + int(dm)
                        if abs_m is not None and int(month) <= abs_m <= int(month_end):
                            record["年份"], record["月份"] = dy, dm
                            record["_sk"] = (int(dy), int(dm))
                        else:
                            record["月份"] = ""
                            record["_sk"] = (int(year), int(month))
                    records.append(record)
        # AO2：行序按（年份, 月份）数字序（原按 source_path 字典序会把 10 月排在 1 月前）；
        # 同（年,月）内保持 SQL 的 source_path/page_number/seq 顺序（稳定排序）
        records.sort(key=_year_month_key)
        for r in records:
            r.pop("_sk", None)  # 排序辅助键不进导出产物
        emit({"phase": "extracted", "records": len(records)})
        merged = len(paths) > 1
        file_label = f"合并导出({len(paths)}库)" if merged else str(path)
        file_hash = _file_hash(paths[0]) if not merged else _file_hash_list(paths)
        return {"file": file_label, "file_hash": file_hash, "kind": "ocr_db",
                "records": records}

    table_units: dict[str, dict] = {}
    text_units: list[dict] = []
    seen_ids: set[str] = set()
    with _open(path) as conn:
        cursor = conn.execute(
            "SELECT source_path, page_number, data FROM records "
            "ORDER BY source_path, page_number, seq"
        )
        for source_path, page_number, data_json in cursor:
            unit = table_units.setdefault(source_path, {
                "unit_id": Path(source_path).name,
                "unit_type": "table",
                "rows": [["字段 (页码)", "值"]],
            })
            try:
                data = json.loads(data_json)
            except (TypeError, json.JSONDecodeError):
                data = {}
            unit["rows"].append([str(page_number), ""])
            for key, value in data.items():
                text = _format_cell(value)
                if len(text) > long_value_chars:
                    uid = f"{Path(source_path).name}·{key}·p{page_number}"
                    n = 2
                    while uid in seen_ids:
                        uid = f"{Path(source_path).name}·{key}·p{page_number}#{n}"
                        n += 1
                    seen_ids.add(uid)
                    text_units.append({
                        "unit_id": uid, "unit_type": "text", "text": text,
                    })
                else:
                    unit["rows"].append([f"{key} (p{page_number})", text])

    units = list(table_units.values()) + text_units
    emit({"phase": "extracted", "units": len(units)})
    return {"file": str(path), "file_hash": _file_hash(path), "kind": "ocr_db", "units": units}
