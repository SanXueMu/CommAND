"""视觉识别（CommOCR pipeline 主链移植）：文档 → VL 识别 → 钩子 → 结果库。

含态机制内化：页级缓存断点续跑 / 连续失败熔断 / 401/403 快败 / 文本型 PDF 跳过。
密钥经 ctx.keys（keys 服务）；结果库与 CommOCR ocr_results.db 完全同构。
渲染在工具内完成（img.pages 不上管线总线——大 payload 裁定）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from command_shared import ocr_engine, ocr_storage
from command_shared.vl_client import make_vl_client
from core.errors import ToolDomainError

DEFAULT_MODEL = "qwen-vl-max"
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _resolve_key(ctx, key_name: str | None) -> dict:
    keys = getattr(ctx, "keys", None) or {}
    if not keys:
        raise ToolDomainError("无可用 LLM 密钥：请先经 /api/keys 注册（keys 服务）")
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
    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")

    key = _resolve_key(ctx, input.get("key_name"))
    base_url = key.get("base_url") or DASHSCOPE_BASE
    client = make_vl_client(key["api_key"], base_url)

    fields = input.get("fields") or ["内容"]
    record_mode = input.get("record_mode") or "page"
    if input.get("raw_prompt"):
        prompt = (input.get("prompt") or "").strip()
        if not prompt:
            raise ToolDomainError("raw_prompt 模式下 prompt 必填（完整提示词，含字段/规则/示例）")
    else:
        prompt = ocr_engine.build_prompt(
            input.get("prompt") or "你是专业的文档识别助手。请仔细识别图片中的全部内容。",
            fields, input.get("rules") or "", input.get("example") or "", record_mode)

    db_path = Path(input["db"]) if input.get("db") else (
        Path(__import__("os").environ.get("COMMAND_DATA_DIR", "data"))
        / "ocr" / f"{path.stem}.ocr_results.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = ocr_storage.connect(db_path)
    try:
        ocr_storage.initialize(connection)

        def progress(phase: str, message: str) -> None:
            emit({"type": "progress", "phase": phase, "message": message})

        stats = ocr_engine.process_document(
            path, connection, client, prompt, fields,
            model=input.get("model") or DEFAULT_MODEL,
            image_format=input.get("image_format") or "jpeg",
            record_mode=record_mode,
            postprocess=input.get("postprocess") or None,
                    lenient_fields=(fields if input.get("lenient")
                            else (input.get("lenient_fields") or None)),
            skip_text_pdf=bool(input.get("skip_text_pdf", True)),
            render_scale=float(input.get("render_scale", 2.0)),
            image_max_side=int(input.get("image_max_side", 2200)),
            page_concurrency=int(input.get("page_concurrency", 3)),
            fail_circuit=int(input.get("fail_circuit", ocr_engine.PAGE_FAIL_CIRCUIT)),
            progress=progress,
        )
        records = ocr_storage.read_records(connection, stats["file_hash"], path.name)
    finally:
        connection.close()

    auth_error = stats.get("auth_error")
    if auth_error and not records:
        raise ToolDomainError(f"认证失败（{auth_error}）：请检查密钥")
    return {
        "file": str(path),
        "file_hash": stats["file_hash"],
        "db": str(db_path),
        "records": records,
        "records_count": len(records),
        "pages_total": stats.get("pages_total", 0),
        "pages_done": stats.get("pages_done", 0),
        "pages_cached": stats.get("pages_cached", 0),
        "skipped_text_pdf": stats.get("skipped_text_pdf", False),
        "failed_pages": stats.get("failed_pages", []),
        "review_notes": stats.get("review_notes", []),
    }
