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
    """AO/AR：从原件文件名提取（年份, 首月, 尾月）三元组，月份两位补零。

    - 单月：2002年3月记账凭证_1_.pdf → ("2002", "03", "")
    - 区间：1993年9月-10月记账凭证.pdf → ("1993", "09", "10")；2001年4-12月 → ("2001", "04", "12")
    AR2：区间文件名的月份列写范围串（"09-10"）。AR3 两位补零（"06-08"）——
    文本升序排序时 "11-12" 不再跑到 "06-08" 前；补零串在导出端按前导零规则
    保留文本单元格（不数值化），排序语义稳定。
    提不到时三元组皆空。
    """
    import re

    name = Path(source_path).name
    m = re.search(
        r"(\d{4})年\s*(\d{1,2})\s*月?\s*[-—~至到]\s*(?:\d{4}年\s*)?(\d{1,2})\s*月", name)
    if m:
        return (m.group(1), f"{int(m.group(2)):02d}", f"{int(m.group(3)):02d}")
    m = re.search(r"(\d{4})年(\d{1,2})月", name)
    return (m.group(1), f"{int(m.group(2)):02d}", "") if m else ("", "", "")


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
                        # 单月（或无名）文件名：文件名权威，两位补零（"03"）
                        record["月份"] = month
                    else:
                        # AR2/AR3：区间文件名——月份列写补零范围串（"06-08"）。
                        # 凭证日期识别率不足，逐条消歧不可靠；文件名范围即权威口径。
                        # 两位补零保证文本升序排序正确（"11-12" 不再跑到 "06-08" 前）。
                        # 排序键取首月（同文件聚组、页序稳定）
                        record["月份"] = f"{month}-{month_end}"
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
