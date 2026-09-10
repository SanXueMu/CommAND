"""OCR 识别引擎主链（CommOCR pipeline.process 移植）：渲染 → VL → 解析校验 → 钩子 → 落库。

含态机制全部内化（与 llm_engine 同裁定）：
- 页级缓存/断点续跑（缓存键 file_hash+source_path+row_number，跳过已存行）
- 连续失败熔断（fail_circuit）、401/403 首页即败（_AuthFail）
- 页级并发（ThreadPoolExecutor；渲染在主线程串行——PyMuPDF 线程安全约束）
- 文本型 PDF 直提跳过（skip_text_pdf）
record 模式：逐页识别后跨页合并为一条记录（比 CommOCR 的整文档多图单请求
对长文档更稳，行为差异已在本会话蓝图裁定记录）。
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from command_shared import ocr_storage
from command_shared.ocr_render import (
    calculate_file_hash,
    is_text_pdf,
    open_document,
    render_page,
)
from command_shared.ocr_validate import compile_page_hook, parse_records, run_page_hooks
from command_shared.vl_client import call_vl

PAGE_FAIL_CIRCUIT = 5
PAGE_RETRIES = 3
AUTH_FAIL_PREFIXES = ("401", "403")


class _AuthFail(Exception):
    pass


def build_prompt(template: str, fields: list[str], rules: str, example: str,
                 record_mode: str) -> str:
    """TaskSpec → VL 提示词（CommOCR 同款装配）。"""
    lines = [template.strip()]
    if record_mode == "record":
        lines.append(
            f"\n请提取页面中与以下字段相关的全部信息，逐字段给出完整内容，"
            f"字段只能是：{json.dumps(fields, ensure_ascii=False)}。"
        )
    else:
        lines.append(
            f"\n请把页面内容按既定结构逐条整理为 JSON 数组，每个元素一个对象，"
            f"字段只能是：{json.dumps(fields, ensure_ascii=False)}；"
            f"页面无有效内容时输出 []。"
        )
    if rules:
        lines.append(f"\n字段规则：\n{rules.strip()}")
    if example:
        lines.append(f"\n输出示例：\n{example.strip()}")
    lines.append("\n只输出 JSON，不要输出其他文字或代码块标记。")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def process_document(
    path,
    connection,
    client,
    prompt: str,
    fields: list[str],
    model: str,
    image_format: str = "jpeg",
    record_mode: str = "page",
    postprocess: list[dict] | None = None,
    lenient_fields: list[str] | None = None,
    skip_text_pdf: bool = True,
    render_scale: float = 2.0,
    image_max_side: int = 2200,
    page_concurrency: int = 3,
    page_retries: int = PAGE_RETRIES,
    fail_circuit: int = PAGE_FAIL_CIRCUIT,
    progress=None,
) -> dict:
    """主链：识别一份文档（PDF/图片）并写入结果库。返回统计 dict。

    progress: callable(phase: str, message: str) 可选。
    """
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在: {src}")

    hooks = [{"name": spec.get("name", "hook"),
              "fn": compile_page_hook(spec.get("name", "hook"), spec["code"])}
             for spec in (postprocess or [])]

    file_hash = calculate_file_hash(src)
    source_path = src.name
    cached = ocr_storage.get_cached_rows(connection, file_hash, source_path)
    stats: dict = {"file": str(src), "file_hash": file_hash, "pages_cached": len(cached)}

    if skip_text_pdf and is_text_pdf(src):
        stats.update({"skipped_text_pdf": True, "pages_total": 0, "pages_done": 0,
                      "failed_pages": [], "records_written": 0, "review_notes": []})
        return stats

    if progress:
        progress("render", f"打开文档: {src.name}")

    page_jobs: list[tuple[int, int, bytes]] = []
    doc = open_document(src)
    try:
        total = doc.page_count
        for index in range(total):
            row_number = index + 1
            if row_number in cached:
                continue
            page = doc.load_page(index)
            image_bytes = render_page(page, render_scale, image_max_side, image_format)
            page_jobs.append((row_number, index + 1, image_bytes))
    finally:
        doc.close()
    stats["pages_total"] = total

    if record_mode == "record":
        stats.update(_process_record_mode(
            client, prompt, fields, model, image_format, hooks, lenient_fields,
            file_hash, source_path, connection, page_jobs, progress))
    else:
        stats.update(_process_page_mode(
            connection, client, prompt, fields, model, image_format, hooks,
            lenient_fields, file_hash, source_path, page_jobs,
            page_concurrency, fail_circuit, progress))
    return stats


def _process_record_mode(client, prompt, fields, model, image_format, hooks,
                         lenient_fields, file_hash, source_path, connection,
                         page_jobs, progress) -> dict:
    """整文档一记录：逐页识别，跨页合并非缺席值（同字段多值 ； 连接）。"""
    failed_pages: list[int] = []
    merged: dict[str, list[str]] = {}
    seen: set[str] = set()
    pages_done = 0
    for row_number, page_number, image_bytes in page_jobs:
        try:
            raw = call_vl(client, prompt, image_bytes, model, image_format)
            records = parse_records(raw, fields, lenient_fields)
        except Exception:
            failed_pages.append(page_number)
            continue
        pages_done += 1
        for record in records:
            for key, value in record.items():
                if key in ("页码", "行号"):
                    continue
                text = str(value).strip()
                if text and text not in ("", "未见", "未出现") and (key, text) not in seen:
                    seen.add((key, text))
                    merged.setdefault(key, []).append(text)
    final: dict = {}
    for key, texts in merged.items():
        final[key] = "；".join(texts)
    notes: list[str] = []
    if hooks and final:
        outcome = run_page_hooks(hooks, final)
        final, notes = outcome["fields"], outcome["notes"]
    if final:
        final["页码"] = page_jobs[0][1] if page_jobs else 1
        ocr_storage.append_records(connection, file_hash, source_path, [(1, final)])
    if progress:
        progress("recognize", f"record 模式完成 {pages_done}/{len(page_jobs)} 页")
    return {"pages_done": pages_done, "failed_pages": failed_pages,
            "records_written": 1 if final else 0, "review_notes": notes}


def _process_page_mode(connection, client, prompt, fields, model, image_format, hooks,
                       lenient_fields, file_hash, source_path, page_jobs,
                       page_concurrency, fail_circuit, progress) -> dict:
    """逐页逐记录：页级并发 + 熔断 + 钩子 + 落库。"""
    failed_pages: list[int] = []
    results: dict[int, tuple] = {}
    consecutive = 0
    auth_error: str | None = None
    review_notes: list[str] = []

    def recognize_page(page_number: int, image_bytes: bytes):
        try:
            raw = call_vl(client, prompt, image_bytes, model, image_format)
            records = parse_records(raw, fields, lenient_fields)
        except Exception as exc:
            message = str(exc)
            if "401" in message or "403" in message:
                raise _AuthFail(message) from exc
            raise
        notes: list[str] = []
        for record in records:
            record["页码"] = page_number
            if hooks:
                outcome = run_page_hooks(hooks, record)
                record = outcome["fields"]
                notes.extend(outcome["notes"])
        return records, notes

    future_map: dict = {}
    stop = False
    pool = ThreadPoolExecutor(max_workers=max(1, page_concurrency))
    try:
        for row_number, page_number, image_bytes in page_jobs:
            if stop:
                break
            future = pool.submit(recognize_page, page_number, image_bytes)
            future_map[future] = (row_number, page_number)
        for future, (row_number, page_number) in future_map.items():
            try:
                records, notes = future.result()
                results[row_number] = (records, notes)
                consecutive = 0
            except _AuthFail as exc:
                auth_error = str(exc)
                failed_pages.append(page_number)
                stop = True
                break
            except Exception:
                consecutive += 1
                failed_pages.append(page_number)
                if consecutive >= fail_circuit:
                    stop = True
                    break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    written = 0
    done = 0
    for row_number, page_number, _ in page_jobs:
        result = results.get(row_number)
        if result is None:
            continue
        records, notes = result
        payload = [(row_number, record) for record in records]
        if payload:
            written += ocr_storage.append_records(connection, file_hash, source_path, payload)
        review_notes.extend(notes)
        done += 1
        if progress and (done % 5 == 0 or done == len(results)):
            progress("recognize", f"已识别 {done} 页")

    return {"pages_done": done, "failed_pages": sorted(set(failed_pages)),
            "records_written": written, "review_notes": review_notes,
            "auth_error": auth_error}
