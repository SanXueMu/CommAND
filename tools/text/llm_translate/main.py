"""LLM 批量翻译（translee engine 真身）：编号直存 + 三路线 + 熔断 + 质检重译 + 字典缓存。

含环/含态机制全部内化（线性管线无环，这是拆分粒度的硬约束）：
- 编号/纯数字直存（不耗 API）；分隔符批翻主路 → JSON 兜底 → 逐条回退
- 对齐失败率超阈值切 JSON 路线；连续 3 批双路线失败熔断
- 质检不过 → 强化指令重译（含指令复述污染防御）；缓存命中只认 ok 条目
密钥经 ctx.keys（keys 服务运行时注入），缓存库位于 COMMAND_DATA_DIR/dict_cache.db。
"""
from __future__ import annotations

from command_shared import dict_cache
from command_shared.llm_engine import (
    DEFAULT_CONCURRENCY,
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_MAX_BATCH_CHARS,
    DEFAULT_MODEL,
    DEFAULT_PREMIUM_MODEL,
    make_client,
    merge_usage,
    translate_texts,
)
from core.errors import ToolDomainError


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


def _parse_terms(raw) -> list[tuple[str, str]]:
    """术语表：接受 [[原文,译文],...] 或字符串（每行「原文 => 译文」，兼容 tab/->/→）。"""
    if not raw:
        return []
    if isinstance(raw, str):
        pairs: list[tuple[str, str]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in ("=>", "\t", "->", "→", "＝"):
                if sep in line:
                    src, _, tgt = line.partition(sep)
                    if src.strip() and tgt.strip():
                        pairs.append((src.strip(), tgt.strip()))
                    break
        return pairs
    out: list[tuple[str, str]] = []
    for t in raw:
        if isinstance(t, (list, tuple)) and len(t) >= 2 and str(t[0]).strip():
            out.append((str(t[0]).strip(), str(t[1]).strip()))
    return out


def run(input: dict, ctx, emit) -> dict:
    segments: list[str] = input["segments"]
    key = _resolve_key(ctx, input.get("key_name"))
    client = make_client(key["api_key"], key.get("base_url") or "")

    model = input.get("model") or DEFAULT_MODEL
    fallback_model = input.get("fallback_model") or DEFAULT_FALLBACK_MODEL
    target_lang = input.get("target_lang") or "Chinese"
    source_lang = input.get("source_lang")
    terms = _parse_terms(input.get("terms"))
    use_cache = input.get("use_cache", True)

    usage_total: dict | None = None
    usage_by_model: dict[str, dict] = {}
    calls = 0
    cache_hits = 0

    def _progress(event: dict) -> None:
        nonlocal usage_total, calls
        if event.get("phase") == "usage":
            pt = event.get("prompt_tokens") or 0
            ct = event.get("completion_tokens") or 0
            usage_total = merge_usage(usage_total, {"prompt_tokens": pt, "completion_tokens": ct})
            calls += 1
            m = event.get("model") or model
            slot = usage_by_model.setdefault(m, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            slot["calls"] += 1
            slot["prompt_tokens"] += pt
            slot["completion_tokens"] += ct
        else:
            emit(event)

    results: dict[str, dict] = {}
    todo_unique: list[str] = []
    term_norms = {t0.strip() for t0, _ in terms if t0 and t0.strip()}

    conn = dict_cache.open_dict() if use_cache else None
    try:
        cached = (
            dict_cache.lookup(conn, [dict_cache.text_key(s) for s in segments])
            if conn is not None
            else {}
        )
        for seg in segments:
            if not seg.strip():
                results[seg] = {"translated": "", "status": "ok", "model": ""}
                continue
            if seg in results:
                continue  # 重复输入段：沿用首个判定
            # 术语原文不走缓存（术语表可随时改，命中旧译文会违背新术语）
            hit = None if seg in term_norms else cached.get(dict_cache.text_key(seg))
            if hit and hit["status"] == "ok":
                results[seg] = {"translated": hit["translated"], "status": hit["status"],
                                "model": hit["model"], "cached": True}
                cache_hits += 1
            elif seg not in todo_unique:
                todo_unique.append(seg)

        if todo_unique:
            engine_out = translate_texts(
                client, todo_unique,
                model=model, fallback_model=fallback_model,
                premium_model=DEFAULT_PREMIUM_MODEL,
                premium=bool(input.get("premium", False)),
                target_lang=target_lang, source_lang=source_lang, terms=terms,
                batch_size=int(input.get("batch_size") or 50),
                concurrency=int(input.get("concurrency") or DEFAULT_CONCURRENCY),
                max_batch_chars=int(input.get("max_batch_chars") or DEFAULT_MAX_BATCH_CHARS),
                on_progress=_progress,
                checkpoint=(
                    lambda items: [
                        dict_cache.save(conn, dict_cache.text_key(norm), norm,
                                        item["translated"], item["model"], item["status"])
                        for norm, item in items.items()
                    ]
                ) if conn is not None else None,
            )
            results.update(engine_out)
    finally:
        if conn is not None:
            conn.close()

    translations = [results[s]["translated"] for s in segments]
    statuses = [results[s]["status"] for s in segments]
    review_count = sum(1 for s in statuses if s != "ok")
    emit({"phase": "translated", "total": len(segments), "review": review_count})
    return {
        "translations": translations,
        "statuses": statuses,
        "model": DEFAULT_PREMIUM_MODEL if input.get("premium") else model,
        "usage": usage_total or {"prompt_tokens": 0, "completion_tokens": 0},
        "usage_by_model": usage_by_model,
        "calls": calls,
        "review_count": review_count,
        "cache_hits": cache_hits,
    }
