"""通用视图引擎（CommOCR views.py 全量移植）：ViewSpec JSON → 过滤/分组/聚合/判定/排序。

数据流：页级记录 →(filters)→ 按页收集非缺席值 → 分组
（none 逐页 / value 按值 / value_run 连续同值段含缺席归前段 / record 逐记录一行）
→ 每组 aggregates + verdict 顺序判定 → sort → 输出行。split 拆表另行分支。

页键：records 模式 int 页码；多文件时调用方注入「文件名」字段后仍用 int 页键
（CommOCR 全库模式的 (source_path, page) 元组键由 API 层承担，工具层统一单文件键）。
"""
from __future__ import annotations

import csv
import io

from pydantic import BaseModel, Field

ABSENT_DEFAULT = ["", "未见", "未出现"]
EVIDENCE_CLIP = 40
_INTERNAL_KEYS = ("页码", "行号")


def _page_num(key) -> int:
    return key if isinstance(key, int) else key[1]


class FilterSpec(BaseModel):
    field: str
    op: str = "contains"  # contains/not_contains/eq/neq/startswith/endswith/regex/contains_any/empty/nonempty
    value: str = ""
    values: list[str] = Field(default_factory=list)


class Condition(BaseModel):
    field: str
    op: str = "nonempty"  # nonempty/empty/contains_any/contains/not_contains/eq/startswith
    value: str = ""
    values: list[str] = Field(default_factory=list)


class WhenSpec(BaseModel):
    all: list[Condition] = Field(default_factory=list)
    any: list[Condition] = Field(default_factory=list)


class RuleSpec(BaseModel):
    label: str
    when: WhenSpec = Field(default_factory=WhenSpec)


class VerdictSpec(BaseModel):
    column: str
    rules: list[RuleSpec] = Field(default_factory=list)  # 顺序匹配，首中即定
    default: str = "不匹配"


class GroupSpec(BaseModel):
    mode: str = "none"  # none/value/value_run/record
    field: str = ""
    blank_joins_previous: bool = True
    untitled_label: str = "（起始无标题页）"


class AggregateSpec(BaseModel):
    column: str
    op: str  # group_key/page/page_start/page_end/page_count/first_value/last_value/count_values/join_values/evidence
    field: str = ""
    sep: str = "；"
    clip: int = EVIDENCE_CLIP


class SortSpec(BaseModel):
    column: str
    order: str = "asc"


class SplitSpec(BaseModel):
    field: str
    untitled_label: str = "（未命名）"
    hide_empty_columns: bool = True


class ViewSpec(BaseModel):
    name: str = ""
    columns: list[str] = Field(default_factory=list)
    absent_values: list[str] = Field(default_factory=lambda: list(ABSENT_DEFAULT))
    filters: list[FilterSpec] = Field(default_factory=list)
    group: GroupSpec = Field(default_factory=GroupSpec)
    aggregates: list[AggregateSpec] = Field(default_factory=list)
    verdict: VerdictSpec | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    split: SplitSpec | None = None


def _clip(value: str, clip: int) -> str:
    if clip and len(value) > clip:
        return value[: clip - 1] + "…"
    return value


def _filter_pass(record: dict, f: FilterSpec) -> bool:
    value = str(record.get(f.field, "")).strip()
    op = f.op
    if op == "empty":
        return value == ""
    if op == "nonempty":
        return value != ""
    if op == "contains":
        return f.value in value
    if op == "not_contains":
        return f.value not in value
    if op == "eq":
        return value == f.value
    if op == "neq":
        return value != f.value
    if op == "startswith":
        return value.startswith(f.value)
    if op == "endswith":
        return value.endswith(f.value)
    if op == "regex":
        import re
        return re.search(f.value, value) is not None
    if op == "contains_any":
        return any(v in value for v in f.values)
    raise ValueError(f"未知过滤算子: {op}")


def _condition_pass(collected: dict, c: Condition) -> bool:
    values = collected.get(c.field, [])
    op = c.op
    if op == "nonempty":
        return len(values) > 0
    if op == "empty":
        return len(values) == 0
    if op == "contains_any":
        return any(any(mark in v for mark in c.values) for v in values)
    if op == "contains":
        return any(c.value in v for v in values)
    if op == "not_contains":
        return all(c.value not in v for v in values)
    if op == "eq":
        return c.value in values
    if op == "startswith":
        return any(v.startswith(c.value) for v in values)
    raise ValueError(f"未知判定算子: {op}")


def _when_pass(collected: dict, when: WhenSpec) -> bool:
    if not all(_condition_pass(collected, c) for c in when.all):
        return False
    if when.any and not any(_condition_pass(collected, c) for c in when.any):
        return False
    return True


def _collect_pages(rows, absent_values):
    """rows: [(page, record)] → {page: {field: [非缺席值]}}（保持出现顺序）。"""
    pages: dict[int, dict[str, list[str]]] = {}
    for page_number, record in sorted(rows, key=lambda r: r[0]):
        slot = pages.setdefault(page_number, {})
        for key, raw in record.items():
            if key in _INTERNAL_KEYS:
                continue
            value = str(raw).strip()
            if value and value not in absent_values:
                bucket = slot.setdefault(key, [])
                if value not in bucket:
                    bucket.append(value)
    return pages


def _build_groups(pages: dict, group: GroupSpec, absent_values):
    """→ [(name, [page...])]，页序构建。"""

    groups: list[dict] = []
    if group.mode == "none":
        return [("", [page]) for page in sorted(pages)]
    if group.mode == "value":
        ordered: dict[str, list[int]] = {}
        for page in sorted(pages):
            values = pages[page].get(group.field, [])
            key = values[0] if values else None
            if key is None and group.blank_joins_previous and ordered:
                ordered[next(reversed(ordered))].append(page)
            else:
                ordered.setdefault(key if key is not None else group.untitled_label, []).append(page)
        return list(ordered.items())
    for page in sorted(pages):
        values = pages[page].get(group.field, [])
        key = values[0] if values else None
        if group.mode == "value_run":
            if key and (not groups or groups[-1]["name"] != key):
                groups.append({"name": key, "pages": [page]})
            elif groups:
                groups[-1]["pages"].append(page)
            else:
                groups.append({"name": group.untitled_label, "pages": [page]})
        else:
            raise ValueError(f"未知分组模式: {group.mode}")
    return [(g["name"], g["pages"]) for g in groups]


def _aggregate(name, page_list, pages, agg: AggregateSpec):
    op = agg.op
    if op == "group_key":
        return name
    if op == "page":
        nums = [_page_num(k) for k in page_list]
        return nums[0] if len(nums) == 1 else f"{nums[0]}-{nums[-1]}"
    if op == "page_start":
        return _page_num(page_list[0])
    if op == "page_end":
        return _page_num(page_list[-1])
    if op == "page_count":
        return len(page_list)
    values = []
    src_field = agg.field or agg.column
    for page in page_list:
        values.extend(pages[page].get(src_field, []))
    if op == "first_value":
        return values[0] if values else ""
    if op == "last_value":
        return values[-1] if values else ""
    if op == "count_values":
        return len(values)
    if op == "join_values":
        return agg.sep.join(_clip(v, agg.clip) for v in values)
    if op == "evidence":
        stamps = []
        for page in page_list:
            for value in pages[page].get(agg.field, []):
                stamp = f"第{_page_num(page)}页：{_clip(value, agg.clip)}"
                if stamp not in stamps:
                    stamps.append(stamp)
        return agg.sep.join(stamps)
    raise ValueError(f"未知聚合算子: {op}")


def _record_value(record: dict, field: str, absent_values) -> str:
    value = str(record.get(field, "")).strip()
    return value if value and value not in absent_values else ""


def _record_rows(rows, spec: ViewSpec) -> list[dict]:
    """record 模式：每条记录一行，页级算子退化为单记录语义。"""
    out_rows = []
    for page, record in rows:
        row = {}
        for agg in spec.aggregates:
            op = agg.op
            src = agg.field or agg.column
            if op == "group_key":
                row[agg.column] = ""
            elif op in ("page", "page_start", "page_end"):
                row[agg.column] = _page_num(page)
            elif op == "page_count":
                row[agg.column] = 1
            elif op == "count_values":
                row[agg.column] = 1 if _record_value(record, src, spec.absent_values) else 0
            elif op == "join_values":
                value = _record_value(record, src, spec.absent_values)
                row[agg.column] = _clip(value, agg.clip) if value else ""
            elif op == "evidence":
                value = _record_value(record, src, spec.absent_values)
                row[agg.column] = f"第{_page_num(page)}页：{_clip(value, agg.clip)}" if value else ""
            elif src in _INTERNAL_KEYS:  # first_value/last_value：行号/页码列直接暴露原值
                row[agg.column] = record.get(src, "")
            else:
                row[agg.column] = _record_value(record, src, spec.absent_values)
        if spec.verdict:
            collected = {
                key: [value]
                for key, raw in record.items()
                if key not in _INTERNAL_KEYS
                for value in [str(raw).strip()]
                if value and value not in spec.absent_values
            }
            label = spec.verdict.default
            for rule in spec.verdict.rules:
                if _when_pass(collected, rule.when):
                    label = rule.label
                    break
            row[spec.verdict.column] = label
        out_rows.append(row)
    return out_rows


def _cell_sort_key(value):
    if isinstance(value, int):
        return (0, value, "")
    return (1, 0, str(value))


def _produced_columns(out_rows) -> list[str]:
    columns: list[str] = []
    for r in out_rows:
        for k in r:
            if k not in columns:
                columns.append(k)
    return columns


def _split_view(rows, spec: ViewSpec) -> dict:
    """split 拆表：按 spec.split.field 记录值分组 → 各组逐记录行 → 组内排序+空列裁剪。"""
    split = spec.split
    assert split is not None
    groups: dict[str, list] = {}
    for pair in rows:
        record = pair[1]
        value = str(record.get(split.field, "")).strip()
        key = value if value and value not in spec.absent_values else split.untitled_label
        groups.setdefault(key, []).append(pair)

    columns_all: list[str] = []
    splits: list[dict] = []
    merged_rows: list[dict] = []
    for key, group_rows in groups.items():
        out_rows = _record_rows(group_rows, spec)
        for s in reversed(spec.sort):
            out_rows.sort(key=lambda r, col=s.column: _cell_sort_key(r.get(col, "")),
                          reverse=(s.order == "desc"))
        columns = _produced_columns(out_rows)
        if split.hide_empty_columns:
            columns = [c for c in columns if any(r.get(c, "") != "" for r in out_rows)]
        splits.append({
            "key": key,
            "columns": columns,
            "rows": [{c: r.get(c, "") for c in columns} for r in out_rows],
        })
        merged_rows.extend(out_rows)
        for c in columns:
            if c not in columns_all:
                columns_all.append(c)
    return {
        "columns": columns_all,
        "rows": [{c: r.get(c, "") for c in columns_all} for r in merged_rows],
        "splits": splits,
    }


def compute_view(rows, spec: ViewSpec) -> dict:
    """执行视图：rows=[(page_number, record)] → {"columns": [...], "rows": [...]}。"""
    rows = list(rows)
    for f in spec.filters:
        rows = [(p, r) for p, r in rows if _filter_pass(r, f)]

    if spec.split is not None:
        return _split_view(rows, spec)
    if spec.group.mode == "record":
        out_rows = _record_rows(rows, spec)
    else:
        pages = _collect_pages(rows, spec.absent_values)
        groups = _build_groups(pages, spec.group, spec.absent_values)

        out_rows = []
        for name, page_list in groups:
            collected: dict[str, list[str]] = {}
            for page in page_list:
                for field, values in pages[page].items():
                    bucket = collected.setdefault(field, [])
                    for value in values:
                        if value not in bucket:
                            bucket.append(value)
            row = {}
            for agg in spec.aggregates:
                row[agg.column] = _aggregate(name, page_list, pages, agg)
            if spec.verdict:
                label = spec.verdict.default
                for rule in spec.verdict.rules:
                    if _when_pass(collected, rule.when):
                        label = rule.label
                        break
                row[spec.verdict.column] = label
            out_rows.append(row)

    for s in reversed(spec.sort):
        out_rows.sort(key=lambda r, col=s.column: _cell_sort_key(r.get(col, "")),
                      reverse=(s.order == "desc"))

    if spec.columns:
        columns = list(spec.columns)
        if out_rows:
            produced: set[str] = set()
            for r in out_rows:
                produced.update(r.keys())
            missing = [c for c in columns if c not in produced]
            if missing:
                raise ValueError(f"输出列未由任何聚合/判定产生: {missing}")
    else:
        columns = _produced_columns(out_rows)

    return {"columns": columns, "rows": [{c: r.get(c, "") for c in columns} for r in out_rows]}


def rows_to_csv(result: dict) -> str:
    """视图结果 → CSV 文本（utf-8-sig 由调用方落盘时处理；含表头）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    columns = result.get("columns", [])
    writer.writerow(columns)
    for row in result["rows"]:
        writer.writerow([row.get(c, "") for c in columns])
    return buffer.getvalue()


BUILTIN_VIEWS = [
    {
        "id": "builtin-voucher",
        "name": "发票凭证视图（内置）",
        "spec": {
            "name": "发票凭证视图",
            "columns": ["月份", "页码", "日期", "凭证类别", "凭证号", "摘要", "总账科目",
                        "明细科目", "借方金额", "贷方金额", "附件", "领款人", "合计大写", "备注"],
            "absent_values": ["", "未见", "未出现"],
            "group": {"mode": "none"},
            "aggregates": [
                {"column": "月份", "op": "first_value"},
                {"column": "页码", "op": "page"},
                {"column": "日期", "op": "first_value"},
                {"column": "凭证类别", "op": "first_value"},
                {"column": "凭证号", "op": "first_value"},
                {"column": "摘要", "op": "first_value"},
                {"column": "总账科目", "op": "first_value"},
                {"column": "明细科目", "op": "first_value"},
                {"column": "借方金额", "op": "first_value"},
                {"column": "贷方金额", "op": "first_value"},
                {"column": "附件", "op": "first_value"},
                {"column": "领款人", "op": "first_value"},
                {"column": "合计大写", "op": "first_value"},
                {"column": "备注", "op": "first_value"},
            ],
            "sort": [{"column": "页码", "order": "asc"}],
        },
    },
    {
        "id": "builtin-contracts-plain",
        "name": "合同清单视图（内置·普通）",
        "spec": {
            "name": "合同清单视图",
            "columns": ["合同名称", "起始页", "结束页", "页数"],
            "absent_values": ["", "未见", "未出现"],
            "group": {"mode": "value", "field": "合同名称线索", "untitled_label": "（无名称页）"},
            "aggregates": [
                {"column": "合同名称", "op": "group_key"},
                {"column": "起始页", "op": "page_start"},
                {"column": "结束页", "op": "page_end"},
                {"column": "页数", "op": "page_count"},
            ],
            "sort": [{"column": "起始页", "order": "asc"}],
        },
    },
    {
        "id": "builtin-approval",
        "name": "审批签单视图（内置）",
        "spec": {
            "name": "审批签单视图",
            "columns": ["文件名", "签单标题", "工程总支出审定金额", "审计单位签字时间", "起始页", "页数"],
            "absent_values": ["", "未见", "未出现"],
            "group": {"mode": "value", "field": "文件名", "untitled_label": "（未知文件）"},
            "aggregates": [
                {"column": "文件名", "op": "group_key"},
                {"column": "签单标题", "op": "first_value"},
                {"column": "工程总支出审定金额", "op": "first_value"},
                {"column": "审计单位签字时间", "op": "first_value"},
                {"column": "起始页", "op": "page_start"},
                {"column": "页数", "op": "page_count"},
            ],
            "sort": [],
        },
    },
    {
        "id": "builtin-contracts",
        "name": "合同关键词视图（内置）",
        "spec": {
            "name": "合同关键词视图",
            "columns": ["合同名称", "起始页", "结束页", "页数", "判定", "人物证据", "类型证据"],
            "absent_values": ["", "未见", "未出现"],
            "group": {
                "mode": "value_run",
                "field": "合同名称线索",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）",
            },
            "aggregates": [
                {"column": "合同名称", "op": "group_key"},
                {"column": "起始页", "op": "page_start"},
                {"column": "结束页", "op": "page_end"},
                {"column": "页数", "op": "page_count"},
                {"column": "人物证据", "op": "evidence", "field": "关键人物出现方式"},
                {"column": "类型证据", "op": "evidence", "field": "类型线索"},
            ],
            "verdict": {
                "column": "判定",
                "rules": [
                    {"label": "命中", "when": {"all": [
                        {"field": "关键人物出现方式", "op": "contains_any",
                         "values": ["项目负责人", "其他身份"]},
                        {"field": "类型线索", "op": "nonempty"},
                    ]}},
                    {"label": "排除", "when": {"all": [
                        {"field": "关键人物出现方式", "op": "nonempty"},
                        {"field": "类型线索", "op": "nonempty"},
                    ]}},
                ],
                "default": "不匹配",
            },
            "filters": [],
            "sort": [],
        },
    },
    {
        "id": "builtin-shenbao-view",
        "name": "决算审定表视图（内置）",
        "spec": {
            "name": "决算审定表视图",
            "columns": ["文件名", "项目名称", "项目编码", "项目类型", "建设方式",
                        "批复概算", "审计调整概算", "实际执行概算",
                        "送审金额", "审计调整金额", "审定金额", "备注", "页码"],
            "absent_values": ["", "未见", "未出现"],
            "group": {"mode": "record"},
            "aggregates": [
                {"column": "文件名", "op": "first_value"},
                {"column": "项目名称", "op": "first_value"},
                {"column": "项目编码", "op": "first_value"},
                {"column": "项目类型", "op": "first_value"},
                {"column": "建设方式", "op": "first_value"},
                {"column": "批复概算", "op": "first_value"},
                {"column": "审计调整概算", "op": "first_value"},
                {"column": "实际执行概算", "op": "first_value"},
                {"column": "送审金额", "op": "first_value"},
                {"column": "审计调整金额", "op": "first_value"},
                {"column": "审定金额", "op": "first_value"},
                {"column": "备注", "op": "first_value"},
                {"column": "页码", "op": "page"},
            ],
            "sort": [],
        },
    },
]
