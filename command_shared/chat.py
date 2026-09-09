"""底层 LLM 对话调用：make_client / call_chat 唯一出口 + 错误分流 + usage 穿透。

移植自 translee engine/chat.py（真实联调沉淀），密钥经参数显式传入（来源：CommAND keys 服务注入 ctx）。

错误分流：
- 401 / 欠费(Arrearage) / 无权限(AccessDenied) → TranslationError 致命中止
- 429 限流(Throttling) / 内容审核 403(DataInspectionFailed) → re-raise 走兜底，任务继续
"""
from __future__ import annotations

from openai import APIStatusError, OpenAI

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class TranslationError(RuntimeError):
    """LLM 任务级致命错误（认证失败 / 连续整批失败熔断）。"""


def make_client(api_key: str, base_url: str = DEFAULT_BASE_URL) -> OpenAI:
    """构建 OpenAI 兼容客户端（默认 DashScope 端点）。"""
    return OpenAI(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL)


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
    """401 一律致命；403/429 中限流与内容审核不算致命（应跳过继续），
    其余 403（欠费 Arrearage / 无权限 AccessDenied 等）中止任务——继续跑全是废调用。"""
    status = getattr(exc, "status_code", None)
    if status == 401:
        return True
    if status in (403, 429):
        detail = error_detail(exc).lower()
        return not (
            "throttl" in detail or "datainspection" in detail or "ratelimit" in detail
        )
    return False


def call_chat(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
    translation_options: dict | None = None,
) -> tuple[str, dict | None]:
    """单次对话调用；致命认证错误（401/欠费/无权限 403）抛 TranslationError 中止。

    qwen-mt 不支持 system 角色：指令统一合并进 user 单消息。
    限流（429/Throttling）与内容审核 403（DataInspectionFailed）不算致命：
    re-raise 原异常走 JSON 兜底/逐条回退，坏条目置 review，任务继续。
    usage = {"prompt_tokens", "completion_tokens"}；上游缺失时为 None。
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
    """累计 token 用量；双方均无则 None。"""
    if not a:
        return b
    if not b:
        return a
    return {k: a[k] + b[k] for k in a}
