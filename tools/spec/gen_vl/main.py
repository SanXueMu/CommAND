"""识别模板生成·方案二（多模态直读）：样例页图 + 需求描述 → 三件套。

qwen-vl 直接看样例（前 N 页渲染），不依赖文字层——扫描件/图片通用。
与 spec.gen.textllm 共用生成提示词与解析（command_shared.spec_gen）。
"""
from __future__ import annotations

import json
from pathlib import Path

from command_shared import chat as chat_mod
from command_shared.ocr_render import is_image_file, open_document, render_page
from command_shared.spec_gen import SPEC_BUILDER_SYSTEM, build_spec_user, parse_spec_json
from command_shared.vl_client import call_vl
from core.errors import ToolDomainError

DEFAULT_MODEL = "qwen-vl-max"


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


def _sample_pages(path: Path, max_pages: int, scale: float) -> list[tuple[int, bytes]]:
    if is_image_file(path):
        return [(1, path.read_bytes())]
    samples = []
    doc = open_document(path)
    try:
        for index in range(min(doc.page_count, max_pages)):
            samples.append((index + 1,
                            render_page(doc.load_page(index), scale, 2200, "jpeg")))
    finally:
        doc.close()
    return samples


def run(input: dict, ctx, emit) -> dict:
    requirement = (input.get("requirement") or "").strip()
    if not requirement:
        raise ToolDomainError("requirement（需求描述）必填")
    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")

    key = _resolve_key(ctx, input.get("key_name"))
    client = chat_mod.make_client(key["api_key"], key.get("base_url") or chat_mod.DEFAULT_BASE_URL)
    model = input.get("model") or DEFAULT_MODEL
    user_prompt = f"{SPEC_BUILDER_SYSTEM}\n\n{build_spec_user(requirement)}"

    pages = _sample_pages(path, int(input.get("max_pages", 3)), float(input.get("render_scale", 2.0)))
    raw, usage = "", None
    for page_number, image_bytes in pages:
        emit({"type": "progress", "phase": "generate",
              "message": f"多模态读取第 {page_number} 页样例"})
        raw = call_vl(client, user_prompt, image_bytes, model, "jpeg")
    try:
        spec = parse_spec_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ToolDomainError(f"三件套解析失败: {exc}") from exc

    return {"task_spec": spec["task_spec"], "postprocess": spec["postprocess"],
            "view_spec": spec["view_spec"], "raw": raw, "model": model,
            "sampled_pages": [p for p, _ in pages], "usage": usage}
