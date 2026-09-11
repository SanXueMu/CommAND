"""视图查询（CommOCR views.py 引擎）：records + ViewSpec → 表行（可拆表）。

纯函数引擎移植（过滤/分组/聚合/判定/排序/split 拆表）；records 每条含 页码。
内置视图现由站点声明（/meta/site 的 builtinViews props）以完整 ViewSpec 下发，前端
点选即填入完整 spec；本工具不接受「视图名字符串」入参（见下方显式校验）。
"""
from __future__ import annotations

import json

from command_shared.ocr_views import ViewSpec, compute_view
from core.errors import ToolDomainError


def run(input: dict, ctx, emit) -> dict:
    records = input["records"]
    if not isinstance(records, list):
        raise ToolDomainError("records 必须为数组")
    raw_spec = input["view_spec"]
    if isinstance(raw_spec, str):
        try:
            raw_spec = json.loads(raw_spec)
        except json.JSONDecodeError as exc:
            raise ToolDomainError(f"view_spec 不是合法 JSON: {exc}") from exc
    if isinstance(raw_spec, str):
        # 历史坑：传视图名（含带引号的 JSON 字符串）必定校验失败，这里给出明确指向
        raise ToolDomainError(f"view_spec 须为 ViewSpec 对象（或其 JSON），不接受视图名字符串：{raw_spec!r}")

    try:
        spec = ViewSpec(**raw_spec)
    except Exception as exc:
        raise ToolDomainError(f"ViewSpec 校验失败: {exc}") from exc

    rows = [
        (int(record.get("页码") or 1), record)
        for record in records
        if isinstance(record, dict)
    ]
    try:
        result = compute_view(rows, spec)
    except ValueError as exc:
        raise ToolDomainError(str(exc)) from exc

    emit({"type": "progress", "phase": "view",
          "message": f"视图「{spec.name or '未命名'}」：{len(result['rows'])} 行"})
    return {**result, "splits": result.get("splits", []), "view_name": spec.name}
