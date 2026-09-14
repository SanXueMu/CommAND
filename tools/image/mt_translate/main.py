"""图片翻译：本地图片 → DashScope 临时上传 → 异步图片翻译（qwen-mt-image）→ 下载译文图。

- 模型默认 `qwen-mt-image-2.0`（0.004 元/张），失败自动降级 `fallback_model`
- RPM=1 模型提交前跨线程限速（默认 60s/张），429 指数退避重试
- 术语表直接对接 `terminologies`（src/tgt）；源或目标至少一方须为中文/英文
- 产物写入 outputs/<handle>/，原图只读
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def _resolve_key(ctx, key_name: str | None) -> dict:
    keys = getattr(ctx, "keys", None) or {}
    if not keys:
        raise _ToolError("无可用密钥：请先经「APIKey管理」注册 DashScope 密钥")
    if key_name:
        entry = keys.get(key_name)
        if entry is None:
            raise ToolPauseError(f"密钥不存在: {key_name}",
                                 hint="请在「设置 → APIKey管理」新增该名称的密钥后点「继续」")
        return entry
    for entry in keys.values():
        if entry.get("is_default"):
            return entry
    return next(iter(keys.values()))


def _ToolError(message: str):
    from core.errors import ToolDomainError, ToolPauseError

    return ToolDomainError(message)


from command_shared import image_translate  # noqa: E402 —— 与工具入口同层导入（inproc）
from core.errors import ToolPauseError, ToolUnavailableError  # noqa: E402


def run(input: dict, ctx, emit) -> dict:
    from command_shared.image_translate import (
        DEFAULT_IMAGE_FALLBACK_MODEL,
        DEFAULT_IMAGE_MODEL,
        ImageTranslateError,
        make_client,
        translate_image,
    )

    path = Path(input["file"])
    if not path.is_file():
        raise _ToolError(f"文件不存在: {path}")

    key = _resolve_key(ctx, input.get("key_name"))
    api_key = (key.get("api_key") or "").strip()
    if not api_key:
        raise _ToolError("密钥缺少 api_key")

    model = input.get("model") or DEFAULT_IMAGE_MODEL
    fallback = input.get("fallback_model")
    if fallback is None:
        fallback = DEFAULT_IMAGE_FALLBACK_MODEL
    source_lang = input.get("source_lang")
    target_lang = input.get("target_lang") or "Chinese"

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc")
    out_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = getattr(ctx, "cancel_event", None)
    cancelled = (lambda: bool(cancel_event and cancel_event.is_set())) if cancel_event is not None else None

    waited = 0.0
    model_used = model

    def on_event(event: dict) -> None:
        nonlocal waited, model_used
        if event.get("phase") == "submit":
            waited += float(event.get("waited_s") or 0)
            model_used = event.get("model") or model_used
        emit(event)

    started = time.monotonic()
    try:
        client = make_client(input.get("base_url") or key.get("base_url"))
        with client:
            result = translate_image(
                client, api_key, path, out_dir,
                model=model, fallback_model=fallback,
                source_lang=source_lang, target_lang=target_lang,
                terms=input.get("terms"), domain_hint=input.get("domain_hint"),
                sensitives=input.get("sensitives"), image_segment=bool(input.get("image_segment")),
                output_name=input.get("output_name"), on_event=on_event, cancelled=cancelled,
            )
    except ImageTranslateError as error:
        # 模型未开通/无权限：重试无意义 → 抛「能力不可用」，由 run 级 on_failure 决定降级
        if image_translate.is_unavailable_error(error):
            raise ToolUnavailableError(f"{error}｜{image_translate.UNAVAILABLE_HINT}") from error
        raise _ToolError(str(error))

    elapsed = round(time.monotonic() - started, 1)
    emit({"phase": "translated", "path": result["path"], "model": result["model"],
          "fallback_used": result["fallback_used"], "elapsed_s": elapsed})
    return {
        **result,
        "source_file": str(path),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "elapsed_s": elapsed,
        "waited_s": round(waited, 1),
    }
