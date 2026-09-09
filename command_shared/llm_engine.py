"""LLM 翻译引擎（translee engine 移植）：并发批翻 + 三路线 + 熔断 + 质检重译。

translate_texts：批切分（条数+字符双预算）→ 并发池动态补位 →
  主力分隔符 → JSON 兜底 → 逐条回退 → 质检重译。
所有配置经显式参数传入（零 settings 依赖），默认值沿用 translee 实测选型。
"""

from __future__ import annotations

import json
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Callable

from openai import APIStatusError, OpenAI

from command_shared.verify import is_code_like, retranslate_prompt, verify_pair

# ---- 默认选型（DashScope 兼容端点实测；可被工具入参覆盖）----
DEFAULT_MODEL = "qwen-mt-flash"
DEFAULT_FALLBACK_MODEL = "qwen3.7-flash"
DEFAULT_PREMIUM_MODEL = "qwen3.7-plus"
DEFAULT_BATCH_SIZE = 50
DEFAULT_CONCURRENCY = 4
DEFAULT_MAX_BATCH_CHARS = 6000
DEFAULT_ALIGN_FAIL_SWITCH = 0.02


class TranslationError(RuntimeError):
    """翻译任务级致命错误（认证失败 / 连续整批失败熔断）。"""


# ---------------------------------------------------------------- 底层调用

def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


def error_detail(exc: Exception) -> str:
    """APIStatusError → 提取错误码与消息（Arrearage/DataInspectionFailed 等）。"""
    body = getattr(exc, "body", None)
    code = msg = ""
    if isinstance(body, dict):
        err = body["error"] if isinstance(body.get("error"), dict) else body
        code = str(err.get("code", "") or "")
        msg = str(err.get("message", "") or "")
    return f"{code or type(exc).__name__}: {msg or exc}"[:200]


def _is_fatal_auth(exc: Exception) -> bool:
    """401 致命；403/429 中限流与内容审核不致命（走兜底继续），其余（欠费/无权限）中止。"""
    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    if status in (403, 429):
        detail = error_detail(exc).lower()
        return not ("throttl" in detail or "datainspection" in detail or "ratelimit" in detail)
    return False


def call_chat(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
    translation_options: dict | None = None,
) -> tuple[str, dict | None]:
    """单次对话调用；致命认证错误抛 TranslationError 中止。

    qwen-mt 不支持 system 角色：指令统一合并进 user 单消息。
    """
    extra: dict = {}
    if translation_options:
        extra["translation_options"] = translation_options
    if json_mode:
        extra["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"{system}\n\n{user}"}],
            extra_body=extra or None,
        )
        u = getattr(resp, "usage", None)
        usage = (
            {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}
            if u
            else None
        )
        return resp.choices[0].message.content or "", usage
    except APIStatusError as exc:
        if _is_fatal_auth(exc):
            raise TranslationError(
                f"任务中止（{exc.status_code}，模型 {model}）{error_detail(exc)}——"
                "请检查该模型的额度/权限或 API_KEY"
            ) from exc
        raise


def merge_usage(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return b
    if not b:
        return a
    return {k: a[k] + b[k] for k in a}


# ---------------------------------------------------------------- 提示词与协议

_SEPARATOR_SPLIT_RE = re.compile(r"###(\d+)###\n?(.*?)(?=###\d+###|$)", re.S)
_MT_LANG_MAP = {"chinese": "zh", "english": "en", "zh": "zh", "en": "en", "auto": "auto"}


def glossary_clause(terms) -> str:
    if not terms:
        return ""
    pairs = "；".join(f"{str(src).strip()} → {str(dst).strip()}" for src, dst in terms)
    return f" Glossary (always use these translations): {pairs}."


def system_prompt(target_lang: str, terms=None) -> str:
    return (
        f"Translate the following text into {target_lang}. "
        "Keep all numbers, codes, currency amounts and proper nouns unchanged. "
        "Keep placeholders like [[DATE_1]] exactly as they are."
        f"{glossary_clause(terms)}"
    )


def json_system(target_lang: str, terms=None) -> str:
    return (
        f"You are a translation engine. Translate each item's text into {target_lang}. "
        "Keep all numbers, codes, currency amounts and proper nouns unchanged. "
        "Keep placeholders like [[DATE_1]] exactly as they are. "
        f"{glossary_clause(terms).strip()} "
        'Respond with JSON only: {"translations": [{"id": <id>, "zh": "<translation>"}]} '
        "with one entry per input item, same ids."
    )


def parse_separator(text: str, count: int) -> list[str] | None:
    segments = _SEPARATOR_SPLIT_RE.findall(text)
    if [int(i) for i, _ in segments] != list(range(1, count + 1)):
        return None
    return [body.strip() for _, body in segments]


def parse_json_array(text: str) -> list[dict] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        arrays = [v for v in data.values() if isinstance(v, list)]
        data = arrays[0] if arrays else None
    if not isinstance(data, list):
        return None
    return data if all(isinstance(item, dict) for item in data) else None


def _lang_options(model: str, source_lang, target_lang) -> dict | None:
    """qwen-mt 用压缩码映射（硬要求 translation_options）；其余模型透传语言对。"""
    src = _MT_LANG_MAP.get((source_lang or "auto").lower(), source_lang or "auto")
    dst = _MT_LANG_MAP.get((target_lang or "").lower(), target_lang or "zh")
    if (model or "").startswith("qwen-mt"):
        return {"source_lang": src, "target_lang": dst}
    return {"source_lang": source_lang, "target_lang": target_lang} if source_lang else None


def call_batch_separator(client, model, texts, source_lang, target_lang, terms=None):
    """分隔符协议一批；对齐失败返回 None。"""
    assert not any("###" in t for t in texts), "分隔符冲突，应走 JSON 路线"
    user = "\n".join(f"###{i}###\n{t}" for i, t in enumerate(texts, start=1))
    raw, usage = call_chat(
        client, model, system_prompt(target_lang, terms), user,
        translation_options=_lang_options(model, source_lang, target_lang),
    )
    return parse_separator(raw, len(texts)), usage


def call_batch_json(client, model, texts, target_lang, terms=None):
    """JSON 兜底一批；按 id 对齐，失败返回 None。"""
    payload = [{"id": i, "text": t} for i, t in enumerate(texts, start=1)]
    raw, usage = call_chat(
        client, model, json_system(target_lang, terms),
        json.dumps(payload, ensure_ascii=False), json_mode=True,
    )
    items = parse_json_array(raw)
    if items is None:
        return None, usage
    by_id = {item.get("id"): str(item.get("zh", "")) for item in items}
    try:
        return [by_id[i] for i in range(1, len(texts) + 1)], usage
    except KeyError:
        return None, usage


def call_single(client, model, text, target_lang, source_lang=None, instruction="", terms=None):
    """逐条重译。"""
    user = f"{instruction}\n{text}" if instruction else text
    raw, usage = call_chat(
        client, model, system_prompt(target_lang, terms), user,
        translation_options=_lang_options(model, source_lang, target_lang),
    )
    return raw.strip(), usage


# ---------------------------------------------------------------- 质检重译（污染防御）

# 指令复述特征（真实事故沉淀：qwen-mt 会把英文重译指令当中文复述/转译回显）
_CONTAMINATION_MARKERS = (
    "Translate the complete text",
    "truncated",
    "Source:",
    "请翻译完整文本",
    "来源：",
    "被截断",
)


def ensure_quality(client, text, dst, target_lang, source_lang, terms, fallback_model, on_progress=None):
    """质检不合格条目的强化重译（固定 fallback 模型）；返回 (最终译文, 是否通过)。"""
    instr = retranslate_prompt(text, verify_pair(text, dst)[1])
    try:
        retry, u = call_single(
            client, fallback_model, text, target_lang, source_lang,
            instruction=instr, terms=terms,
        )
    except TranslationError:
        raise
    except Exception:
        return dst, False  # 重译路线异常：保原译文标 review，不中断任务
    if u and on_progress:
        on_progress({"phase": "usage", "model": fallback_model, **u})
    if any(m in retry for m in _CONTAMINATION_MARKERS):
        return dst, False  # 指令被复述/转译 = 污染输出，弃用
    if verify_pair(text, retry)[0]:
        return retry, True
    return dst, False


# ---------------------------------------------------------------- 引擎主循环

def translate_texts(
    client: OpenAI,
    texts: list[str],
    *,
    model: str = DEFAULT_MODEL,
    fallback_model: str = DEFAULT_FALLBACK_MODEL,
    premium_model: str = DEFAULT_PREMIUM_MODEL,
    premium: bool = False,
    target_lang: str = "Chinese",
    source_lang: str | None = None,
    terms: list | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_batch_chars: int = DEFAULT_MAX_BATCH_CHARS,
    align_fail_switch: float = DEFAULT_ALIGN_FAIL_SWITCH,
    on_progress: Callable[[dict], None] | None = None,
    checkpoint: Callable[[dict], None] | None = None,
) -> dict[str, dict]:
    """翻译一批文本 → {文本: {"translated", "status", "model"}}。

    premium=True 用高价值长文模型。status: ok / review（质检未过，已尽力重译）。
    checkpoint(new_items)：每批完成即回调，供调用方增量写缓存（断点续跑）。
    """
    model = premium_model if premium else model
    results: dict[str, dict] = {}
    pending = [t for t in texts if t.strip()]

    # 编号/纯数字直存：不耗 API，缓存幂等（重跑零成本）
    translatable: list[str] = []
    for t in pending:
        if is_code_like(t):
            item = {"translated": t, "status": "ok", "model": "identity"}
            results[t] = {**item, "cached": False}
            if checkpoint:
                checkpoint({t: item})
        else:
            translatable.append(t)
    pending = translatable
    if not pending:
        for text in texts:
            if not text.strip():
                results[text] = {"translated": "", "status": "ok", "model": ""}
        return results

    # 批切分：条数 + 字符双预算（长值自动细分批，防单批延迟爆炸）
    batches: list[list[str]] = []
    cur: list[str] = []
    cur_chars = 0
    for t in pending:
        if cur and (len(cur) >= batch_size or cur_chars + len(t) > max_batch_chars):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(t)
        cur_chars += len(t)
    if cur:
        batches.append(cur)

    state: dict[str, Any] = {
        "align_fails": 0, "batches_done": 0, "route_json": False,
        "consecutive_failures": 0, "done": 0,
    }

    def _emit(phase: str, message: str = "") -> None:
        if on_progress:
            on_progress({"done": state["done"], "total": len(pending), "phase": phase, "message": message})

    def _call_batch(batch_texts: list[str], use_json: bool) -> dict:
        """线程内单批调用：主力 → JSON 兜底。"""
        sep_done = sep_align_fail = False
        translated = None
        used = model
        usage: dict | None = None
        err_sep = None
        if not use_json and "###" not in "".join(batch_texts):
            try:
                translated, u = call_batch_separator(client, model, batch_texts, source_lang, target_lang, terms)
                usage = merge_usage(usage, u)
                sep_done = True
                sep_align_fail = translated is None
            except TranslationError as exc:
                return {"out": None, "model": used, "usage": usage, "sep_done": sep_done,
                        "sep_align_fail": sep_align_fail, "error": str(exc), "fatal": True}
            except Exception as exc:
                err_sep = f"主力路线 {type(exc).__name__}: {exc}"
                translated = None
        if translated is None:
            used = fallback_model
            try:
                translated, u = call_batch_json(client, used, batch_texts, target_lang, terms)
                usage = merge_usage(usage, u)
            except TranslationError as exc:
                return {"out": None, "model": used, "usage": usage, "sep_done": sep_done,
                        "sep_align_fail": sep_align_fail,
                        "error": f"{err_sep}；{exc}" if err_sep else str(exc), "fatal": True}
            except Exception as exc:
                err_fb = f"兜底路线 {type(exc).__name__}: {exc}"
                return {"out": None, "model": used, "usage": usage, "sep_done": sep_done,
                        "sep_align_fail": sep_align_fail,
                        "error": f"{err_sep}；{err_fb}" if err_sep else err_fb}
        return {"out": translated, "model": used, "usage": usage, "sep_done": sep_done,
                "sep_align_fail": sep_align_fail, "error": err_sep}

    next_batch = 0
    running: dict = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:

        def _fill() -> None:
            nonlocal next_batch
            while next_batch < len(batches) and len(running) < concurrency:
                running[pool.submit(_call_batch, batches[next_batch], state["route_json"])] = batches[next_batch]
                next_batch += 1

        _fill()
        while running:
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in finished:
                batch_texts = running.pop(fut)
                r = fut.result()
                if r["sep_done"]:
                    state["batches_done"] += 1
                    if r["sep_align_fail"]:
                        state["align_fails"] += 1
                if r["error"]:
                    _emit("batch_error", r["error"])
                    if not r["out"]:
                        state["consecutive_failures"] += 1
                        if state["consecutive_failures"] >= 3:
                            for f2 in running:
                                f2.cancel()
                            raise TranslationError(
                                f"连续 {state['consecutive_failures']} 批两条路线均失败，熔断中止"
                            )
                else:
                    state["consecutive_failures"] = 0
                if (
                    state["batches_done"] >= 3
                    and state["align_fails"] / state["batches_done"] > align_fail_switch
                ):
                    state["route_json"] = True
                    _emit("route_switch", "对齐失败率超阈值，切换 JSON 兜底路线")
                if r["usage"] and on_progress:
                    on_progress({"phase": "usage", "model": r["model"], **r["usage"]})

                out = r["out"]
                used_model = r["model"]
                batch_usage = r["usage"]
                if out is None:
                    # 整批逐条回退（两路线均异常；单条失败置空，不中断任务）
                    out = []
                    for text in batch_texts:
                        try:
                            dst_txt, u = call_single(client, used_model, text, target_lang, source_lang, terms=terms)
                            batch_usage = merge_usage(batch_usage, u)
                            out.append(dst_txt)
                        except TranslationError:
                            raise
                        except Exception:
                            out.append("")
                if batch_usage and on_progress:
                    on_progress({"phase": "usage", "model": used_model, **batch_usage})

                batch_items: dict[str, dict] = {}
                for text, dst in zip(batch_texts, out):
                    ok, _ = verify_pair(text, dst)
                    if not ok:
                        dst, ok = ensure_quality(
                            client, text, dst, target_lang, source_lang, terms,
                            fallback_model, on_progress,
                        )
                    results[text] = {
                        "translated": dst if ok else (dst or ""),
                        "status": "ok" if ok else "review",
                        "model": used_model,
                    }
                    batch_items[text] = results[text]
                state["done"] += len(batch_texts)
                _emit("translate", used_model)
                if checkpoint:
                    checkpoint(batch_items)
            _fill()

    for text in texts:
        if not text.strip():
            results[text] = {"translated": "", "status": "ok", "model": ""}
    return results
