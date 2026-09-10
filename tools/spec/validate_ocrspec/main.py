"""三件套校验（spec.validate.ocrspec）：模板生成产出的守门员。

校验：fields 非空且为字符串数组；record_mode 合法；钩子可编译且定义 transform_page(records, ctx)；
ViewSpec 可实例化 + 空行干跑（算子合法性）；view 列与 fields 交叉引用一致性（警告级）。
"""
from __future__ import annotations

from command_shared.ocr_validate import HookError, compile_page_hook
from command_shared.ocr_views import ViewSpec, compute_view
from core.errors import ToolDomainError

KNOWN_AGG_OPS = {"group_key", "page", "page_start", "page_end", "page_count",
                 "first_value", "last_value", "count_values", "join_values", "evidence"}


def run(input: dict, ctx, emit) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    task_spec = input.get("task_spec") or {}
    postprocess = input.get("postprocess") or []
    view_spec = input.get("view_spec") or {}

    fields = task_spec.get("fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f for f in fields):
        errors.append("task_spec.fields 必须为非空字符串数组")
        fields = []
    if task_spec.get("record_mode") not in (None, "page", "record"):
        errors.append(f"record_mode 只能 page/record，得到 {task_spec.get('record_mode')}")

    hooks = []
    for index, spec in enumerate(postprocess):
        code = spec.get("code") if isinstance(spec, dict) else None
        try:
            hooks.append(compile_page_hook(spec.get("name", f"hook{index}"), code))
        except HookError as exc:
            errors.append(f"postprocess[{index}] 钩子不可编译: {exc}")

    view = None
    if view_spec:
        try:
            view = ViewSpec(**view_spec)
            compute_view([], view)  # 空行干跑：未知算子/聚合列在此暴露
        except Exception as exc:
            errors.append(f"view_spec 不可执行: {exc}")

    if view is not None and fields:
        produced = {agg.column for agg in view.aggregates} | (
            {view.verdict.column} if view.verdict else set())
        unknown = [c for c in view.columns if c and c not in produced]
        if unknown:
            warnings.append(f"view 列未由聚合/判定产生: {unknown}")
        referenced = {agg.field for agg in view.aggregates if agg.field} | (
            {rule.field for rule in view.verdict.rules for cond in (rule.when.all + rule.when.any)
             for rule_cond in [cond]} if view.verdict else set())
        missing = [f for f in referenced if f not in fields]
        if missing:
            warnings.append(f"view 引用了 fields 之外的字段（识别端可能产不出）: {missing}")
    for agg in (view.aggregates if view else []):
        if agg.op not in KNOWN_AGG_OPS:
            errors.append(f"未知聚合算子: {agg.op}")

    valid = not errors
    emit({"type": "progress", "phase": "validate",
          "message": ("三件套校验通过" if valid else f"校验失败 {len(errors)} 项")
                     + (f"，警告 {len(warnings)} 项" if warnings else "")})
    return {"valid": valid, "errors": errors, "warnings": warnings,
            "fields": fields, "hooks_count": len(hooks)}
