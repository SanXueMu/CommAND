"""图片翻译（批量）：图片序列 → 译文图片序列（图片翻译链第 2 步）。

- 逐张复用单图流程（getPolicy 上传 → 异步提交 → 轮询 → 下载译文图）
- 并发 `concurrency`（默认 2，对齐平台并发上限）+ 全局 RPM 限速（默认 60）
- 逐页回报：单页失败不中断整批；全部失败才抛错（附各页原因摘要）
- 页数 > QUEUE_MAX(500，平台异步队列上限) 直接拒绝并提示拆分
- 源图只读；译文图写入 `outputs/<handle>/tmp_mt_images/`（中间产物，末步清理）
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _error(message: str):
    from core.errors import ToolDomainError, ToolPauseError

    return ToolDomainError(message)


from command_shared import image_translate  # noqa: E402
from core.errors import ToolPauseError, ToolUnavailableError  # noqa: E402


def _resolve_key(ctx, key_name: str | None) -> dict:
    keys = getattr(ctx, "keys", None) or {}
    if not keys:
        raise _error("无可用密钥：请先经「APIKey管理」注册 DashScope 密钥")
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


def run(input: dict, ctx, emit) -> dict:
    from command_shared.image_translate import (
        DEFAULT_CONCURRENCY,
        DEFAULT_IMAGE_FALLBACK_MODEL,
        DEFAULT_IMAGE_MODEL,
        DEFAULT_RPM,
        QUEUE_MAX,
        ImageTranslateError,
        make_client,
        translate_image,
    )

    raw = input.get("images") or []
    if not isinstance(raw, list) or not raw:
        raise _error("images 不能为空")
    paths = [Path(str(p)) for p in raw]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise _error(f"图片不存在: {missing[0]}" + (f"（等 {len(missing)} 个）" if len(missing) > 1 else ""))
    if len(paths) > QUEUE_MAX:
        raise _error(
            f"共 {len(paths)} 页，超过图片翻译单任务上限 {QUEUE_MAX} 页（平台异步队列上限），请拆分后重试"
        )

    key = _resolve_key(ctx, input.get("key_name"))
    api_key = (key.get("api_key") or "").strip()
    if not api_key:
        raise _error("密钥缺少 api_key")

    model = input.get("model") or DEFAULT_IMAGE_MODEL
    fallback = input.get("fallback_model")
    if fallback is None:
        fallback = DEFAULT_IMAGE_FALLBACK_MODEL
    concurrency = max(1, min(int(input.get("concurrency") or DEFAULT_CONCURRENCY), 8))
    rpm = input.get("rpm")
    rpm = DEFAULT_RPM if rpm is None else int(rpm)

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc") / str(input.get("dir_name") or "tmp_mt_images")
    out_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = getattr(ctx, "cancel_event", None)
    cancelled = (lambda: bool(cancel_event and cancel_event.is_set())) if cancel_event is not None else None

    started = time.monotonic()
    results: list[dict | None] = [None] * len(paths)
    done = {"n": 0}

    def one(client, index: int, source: Path) -> dict:
        entry: dict = {"index": index + 1, "source": str(source), "path": None, "ok": False,
                       "model": model, "fallback_used": None, "error": None}
        if cancelled and cancelled():
            entry["error"] = "已取消"
            return entry
        try:
            result = translate_image(
                client, api_key, source, out_dir,
                model=model, fallback_model=fallback,
                source_lang=input.get("source_lang"), target_lang=input.get("target_lang") or "Chinese",
                terms=input.get("terms"), domain_hint=input.get("domain_hint"),
                sensitives=input.get("sensitives"), image_segment=bool(input.get("image_segment")),
                rpm=rpm, cancelled=cancelled,
            )
            entry.update(path=result["path"], ok=True, model=result.get("model"),
                         fallback_used=result.get("fallback_used"))
        except ImageTranslateError as error:
            entry["error"] = str(error)
        except Exception as error:  # noqa: BLE001 —— 单页异常不拖垮整批
            entry["error"] = f"{type(error).__name__}: {error}"
        return entry

    # 共享一个客户端（httpx.Client 线程安全）：避免每页建连，也便于统一超时
    with make_client(input.get("base_url") or key.get("base_url")) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(one, client, i, p) for i, p in enumerate(paths)]
            unavailable: str | None = None
            for future in futures:
                entry = future.result()
                results[entry["index"] - 1] = entry
                done["n"] += 1
                if entry["ok"]:
                    emit({"phase": "translated", "done": done["n"], "total": len(paths),
                          "page": entry["index"], "path": entry["path"]})
                else:
                    emit({"phase": "page_failed", "done": done["n"], "total": len(paths),
                          "page": entry["index"], "error": entry["error"]})
                    # 能力不可用（模型未开通/无权限）→ 立刻停：不必把其余几十页都试一遍
                    # （线上：24 页 × 403，白等一圈才降级）
                    if unavailable is None and image_translate.is_unavailable_error(entry["error"]):
                        unavailable = str(entry["error"])
                        for pending in futures:
                            pending.cancel()
                        break

    items = [r for r in results if r is not None]
    ok_items = [r for r in items if r["ok"]]
    elapsed = round(time.monotonic() - started, 1)
    if unavailable is not None and not ok_items:
        raise ToolUnavailableError(
            f"图片翻译不可用（已提前中止）：{unavailable[:160]}｜"
            f"{image_translate.UNAVAILABLE_HINT}")
    if not ok_items:
        reasons = "；".join(f"第{r['index']}页 {r['error']}" for r in items[:3])
        message = f"全部 {len(items)} 页翻译失败：{reasons}"
        # 全是「模型不可用」类原因 → 交给 run 级 on_failure 降级（如图片流→版式流）
        if image_translate.is_unavailable_error(" ".join(str(r.get("error") or "") for r in items)):
            raise ToolUnavailableError(f"{message[:160]}｜{image_translate.UNAVAILABLE_HINT}")
        raise _error(message)

    emit({"phase": "batch_done", "ok": len(ok_items), "failed": len(items) - len(ok_items), "elapsed_s": elapsed})
    return {
        "count": len(paths),
        "ok_count": len(ok_items),
        "failed": len(items) - len(ok_items),
        "output_dir": str(out_dir),
        "elapsed_s": elapsed,
        "usage": {"image_count": len(ok_items)},
        "paths": [r["path"] for r in ok_items],
        "images": items,
    }
