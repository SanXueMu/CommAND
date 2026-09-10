"""识别模板生成·方案一（纯语言 LLM）：布局分析 JSON + 需求描述 → 三件套。

非 LLM 工具（layout.analyze.pdf）先"看"文档，纯语言模型只做配置推理——
对无文字层的扫描图无能为力，届时走 spec.gen.vl。
"""
from __future__ import annotations

import json
from pathlib import Path

from command_shared import chat as chat_mod
from command_shared.spec_gen import SPEC_BUILDER_SYSTEM, build_spec_user, parse_spec_json
from core.errors import ToolDomainError

DEFAULT_MODEL = "qwen-plus"


def _resolve_key(ctx, key_name: str | None) -> dict:
    keys = getattr(ctx, "keys", None) or {}
    if not keys:
        raise ToolDomainError("无可用 LLM 密钥：请先经 /api/keys 注册")
    if key_name:
        entry = keys.get(key_name)
        if entry is None:
            raise ToolDomainError(f"密钥不存在: {key_name}")
        return entry
    for entry in keys.values():
        if entry.get("is_default"):
            return entry
    return next(iter(keys.values()))


def run(input: dict, ctx, emit) -> dict:
    requirement = (input.get("requirement") or "").strip()
    if not requirement:
        raise ToolDomainError("requirement（需求描述）必填")
    layout_json = input.get("layout_json")
    if not layout_json and input.get("layout"):
        layout_json = json.dumps(input["layout"], ensure_ascii=False)
    if not layout_json:
        raise ToolDomainError("需提供 layout 或 layout_json（由 layout.analyze.pdf 产出）")

    key = _resolve_key(ctx, input.get("key_name"))
    client = chat_mod.make_client(key["api_key"], key.get("base_url") or chat_mod.DEFAULT_BASE_URL)
    model = input.get("model") or DEFAULT_MODEL

    emit({"type": "progress", "phase": "generate", "message": f"调用 {model} 生成三件套"})
    raw, usage = chat_mod.call_chat(
        client, model, SPEC_BUILDER_SYSTEM,
        build_spec_user(requirement, layout_json), json_mode=bool(input.get("json_mode", True)))
    try:
        spec = parse_spec_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ToolDomainError(f"三件套解析失败: {exc}") from exc

    return {"task_spec": spec["task_spec"], "postprocess": spec["postprocess"],
            "view_spec": spec["view_spec"], "raw": raw, "model": model, "usage": usage}
