"""视图查询（CommOCR views.py 引擎）：records + ViewSpec → 表行（可拆表）。

纯函数引擎移植（过滤/分组/聚合/判定/排序/split 拆表）；records 每条含 页码。
内置五视图定义见 command_shared.ocr_views.BUILTIN_VIEWS（模板=管线预选用）。
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
    return {**result, "view_name": spec.name}
