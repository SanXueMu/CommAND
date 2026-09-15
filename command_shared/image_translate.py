"""qwen-mt-image 图片翻译（DashScope 原生异步 API，图片进 → 图片出）。

链路：本地图片 → getPolicy 取临时上传凭证 → OSS 直传 → 提交异步图片翻译任务 →
      轮询 /tasks/{task_id} → 下载译文图到本地。

要点（实测/官方约束）：
- 只能异步（`X-DashScope-Async: enable`），必须轮询取结果；结果 URL 24h 失效
- 源或目标语言至少一方为中文/英文，否则报错
- `qwen-mt-image-2.0` RPM = 1 → 提交前跨线程限速（默认 60s），并做 429 指数退避
- 模型不可用 / 任务失败 → 自动降级 `fallback_model`（同端点，仅 model 名不同）
- 所有 HTTP 调用显式超时（避免请求静默挂死）
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import httpx

from command_shared.glossary import as_terminologies

DEFAULT_IMAGE_MODEL = "qwen-mt-image-2.0"
DEFAULT_IMAGE_FALLBACK_MODEL = "qwen-mt-image"
DEFAULT_BASE = "https://dashscope.aliyuncs.com"
ASYNC_ENDPOINT = "/api/v1/services/aigc/image2image/image-synthesis"
UPLOAD_POLICY_ENDPOINT = "/api/v1/uploads"
TASK_ENDPOINT = "/api/v1/tasks"

TIMEOUT_S = 120.0
POLL_INTERVAL_S = 3.0
POLL_BUDGET_S = 900.0
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BASE_SLEEP = 5.0

# 限速与并发（来源：通义千问平台 qwen-mt-image-2.0 模型页：RPM 60 / 并发 2 / 异步队列上限 500）
DEFAULT_RPM = 60            # 每分钟请求数（提交间隔 = 60/rpm 秒）
DEFAULT_CONCURRENCY = 2     # 同时在飞的任务数
QUEUE_MAX = 500             # 云端异步队列上限（单任务页数硬上限）
SUBMIT_WAVE = 100           # 分波提交：每波任务数（避免把云端队列一次打满）
_LANG_CODES = {
    "chinese": "zh", "zh": "zh", "zh-cn": "zh", "中文": "zh",
    "english": "en", "en": "en", "英文": "en",
    "japanese": "ja", "ja": "ja", "korean": "ko", "ko": "ko",
    "spanish": "es", "es": "es", "french": "fr", "fr": "fr",
    "german": "de", "de": "de", "russian": "ru", "ru": "ru",
    "portuguese": "pt", "pt": "pt", "italian": "it", "it": "it",
    "thai": "th", "th": "th", "vietnamese": "vi", "vi": "vi",
    "arabic": "ar", "ar": "ar", "auto": "auto", "自动": "auto",
}

_rate_lock = threading.Lock()
_last_submit: dict[str, float] = {}


class ImageTranslateError(RuntimeError):
    """图片翻译任务级错误（上传/提交/轮询失败或超时）。"""


# ---------------------------------------------------------------- 工具函数

def native_base(base_url: str | None) -> str:
    """把 OpenAI 兼容 base（.../compatible-mode/v1）折回 DashScope 原生 base。"""
    raw = (base_url or "").strip()
    if not raw:
        return DEFAULT_BASE
    base = raw.rstrip("/")
    for suffix in ("/compatible-mode/v1", "/compatible-mode", "/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base or DEFAULT_BASE


def lang_code(value: str | None) -> str | None:
    """语言名/代码 → DashScope 语言码（未知值原样透传，交由服务端校验）。"""
    text = (value or "").strip()
    if not text:
        return None
    return _LANG_CODES.get(text.lower(), text)


def check_lang_pair(source_lang: str | None, target_lang: str | None) -> None:
    """源或目标至少一方须为中文/英文（qwen-mt-image 的硬约束）。"""
    src, tgt = lang_code(source_lang), lang_code(target_lang)
    # auto（未指定）视为可能命中中/英，放行
    if src and tgt and "auto" not in (src, tgt) and src not in ("zh", "en") and tgt not in ("zh", "en"):
        raise ImageTranslateError(
            f"图片翻译要求源或目标至少一方为中文/英文（当前 {src} → {tgt}）")


def throttle(model: str, min_interval_s: float | None = None, rpm: int | None = None) -> float:
    """跨线程限速：返回实际等待秒数。

    间隔优先取 min_interval_s；否则按 rpm 推导（60/rpm 秒，rpm<=0 表示不限速）。
    """
    interval = min_interval_s
    if interval is None:
        effective_rpm = DEFAULT_RPM if rpm is None else rpm
        interval = 60.0 / effective_rpm if effective_rpm and effective_rpm > 0 else 0.0
    if interval <= 0:
        return 0.0
    with _rate_lock:
        waited = 0.0
        now = time.monotonic()
        last = _last_submit.get(model)
        if last is not None:
            gap = now - last
            if gap < interval:
                waited = interval - gap
                time.sleep(waited)
        _last_submit[model] = time.monotonic()
    return waited


def make_client(base_url: str | None = None, timeout: float = TIMEOUT_S) -> httpx.Client:
    return httpx.Client(base_url=native_base(base_url), timeout=timeout, follow_redirects=True)


def _headers(api_key: str, *, async_call: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if async_call:
        headers["X-DashScope-Async"] = "enable"
    return headers


def _post_with_retry(client: httpx.Client, url: str, *, headers: dict, **kwargs) -> httpx.Response:
    """429/5xx 指数退避重试；其余错误立即抛出。"""
    last: Exception | None = None
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            resp = client.post(url, headers=headers, **kwargs)
        except httpx.HTTPError as error:
            last = error
            if attempt >= RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_BASE_SLEEP * (2 ** attempt))
            continue
        if resp.status_code < 400:
            return resp
        if resp.status_code == 429 or resp.status_code >= 500:
            last = ImageTranslateError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if attempt >= RATE_LIMIT_RETRIES:
                break
            time.sleep(RATE_LIMIT_BASE_SLEEP * (2 ** attempt))
            continue
        raise ImageTranslateError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    raise ImageTranslateError(f"请求重试 {RATE_LIMIT_RETRIES} 次仍失败: {last}")


def upload_image(client: httpx.Client, api_key: str, model: str, path: Path) -> str:
    """取临时上传凭证 → OSS 直传 → 返回可被 DashScope 引用的 `oss://` 地址。"""
    resp = client.get(UPLOAD_POLICY_ENDPOINT,
                      params={"action": "getPolicy", "model": model},
                      headers=_headers(api_key))
    if resp.status_code >= 400:
        raise ImageTranslateError(f"获取上传凭证失败 HTTP {resp.status_code}: {resp.text[:300]}")
    policy = (resp.json() or {}).get("data") or {}
    upload_host = (policy.get("upload_host") or "").rstrip("/")
    upload_dir = (policy.get("upload_dir") or "").strip("/")
    if not upload_host or not upload_dir:
        raise ImageTranslateError(f"上传凭证不完整: {policy}")

    key = f"{upload_dir}/{path.name}"
    fields = {
        "key": key,
        "policy": policy.get("policy", ""),
        "OSSAccessKeyId": policy.get("oss_access_key_id", ""),
        "signature": policy.get("signature", ""),
        "x-oss-object-acl": policy.get("x_oss_object_acl", ""),
        "x-oss-forbid-overwrite": str(policy.get("x_oss_forbid_overwrite", "true")).lower(),
        "success_action_status": "200",
    }
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, "application/octet-stream")}
        resp = client.post(upload_host, data=fields, files=files)
    if resp.status_code >= 400:
        raise ImageTranslateError(f"上传图片失败 HTTP {resp.status_code}: {resp.text[:300]}")
    return f"oss://{key}"


def submit_task(client: httpx.Client, api_key: str, *, model: str, image_url: str,
                source_lang: str | None, target_lang: str | None, terms=None,
                domain_hint: str | None = None, sensitives=None,
                image_segment: bool = False) -> str:
    """提交异步图片翻译任务 → task_id。"""
    payload: dict = {"model": model, "input": {"image_url": image_url}}
    src, tgt = lang_code(source_lang), lang_code(target_lang)
    if src:
        payload["input"]["source_lang"] = src
    if tgt:
        payload["input"]["target_lang"] = tgt
    ext: dict = {}
    if domain_hint:
        ext["domainHint"] = domain_hint
    if sensitives:
        ext["sensitives"] = list(sensitives)
    terminologies = as_terminologies(terms)
    if terminologies:
        ext["terminologies"] = terminologies
    if image_segment:
        ext["config"] = {"imageSegment": True}
    if ext:
        payload["input"]["ext"] = ext

    resp = _post_with_retry(client, ASYNC_ENDPOINT, headers=_headers(api_key, async_call=True), json=payload)
    task_id = ((resp.json() or {}).get("output") or {}).get("task_id")
    if not task_id:
        raise ImageTranslateError(f"提交任务未返回 task_id: {resp.text[:300]}")
    return task_id


def wait_task(client: httpx.Client, api_key: str, task_id: str, *,
              budget_s: float = POLL_BUDGET_S, poll_interval_s: float = POLL_INTERVAL_S,
              on_poll=None, cancelled=None) -> str:
    """轮询到终态 → 译文图 URL。FAILED/超时抛错；cancelled() 为真时中止。"""
    deadline = time.monotonic() + budget_s
    while True:
        if cancelled is not None and cancelled():
            raise ImageTranslateError("任务已取消")
        resp = client.get(f"{TASK_ENDPOINT}/{task_id}", headers=_headers(api_key))
        if resp.status_code >= 400:
            raise ImageTranslateError(f"查询任务失败 HTTP {resp.status_code}: {resp.text[:300]}")
        output = (resp.json() or {}).get("output") or {}
        status = (output.get("task_status") or "").upper()
        if on_poll is not None:
            on_poll(status, output)
        if status == "SUCCEEDED":
            results = output.get("results") or []
            url = (results[0] or {}).get("url") if results else None
            if not url:
                raise ImageTranslateError(f"任务成功但无结果 URL: {output}")
            return url
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise ImageTranslateError(
                f"任务 {status}: {output.get('message') or output.get('code') or output}")
        if time.monotonic() > deadline:
            raise ImageTranslateError(f"轮询超时（{int(budget_s)}s，最后状态 {status or '未知'}）")
        time.sleep(poll_interval_s)


def download(client: httpx.Client, url: str, dest: Path) -> Path:
    """下载译文图到本地（结果 URL 24h 失效，必须立即落盘）。"""
    resp = client.get(url)
    if resp.status_code >= 400:
        raise ImageTranslateError(f"下载译文图失败 HTTP {resp.status_code}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


# 「能力不可用」判据：模型未开通 / 无权限 / 模型名不存在——重试无意义，应触发 run 级降级
_UNAVAILABLE_HINTS = (
    "model not found", "model does not exist", "invalid model", "model not available",
    "no permission", "not authorized", "access denied", "forbidden", "unauthorized",
    "未开通", "无权限", "没有权限", "模型不存在",
)


UNAVAILABLE_HINT = (
    "该密钥无图片翻译模型（qwen-mt-image）权限：请在百炼控制台为该 Key 放开模型限制，"
    "或改用其它密钥。扫描件/图片也可以不改密钥："
    "① PDF 选「全部文档翻译」口径（自动补文字层后翻译，产出双语 docx）；"
    "② 图片先转成 PDF，再选「全部文档翻译」或「版式翻译」。"
)


def is_unavailable_error(error: BaseException | str | None) -> bool:
    """判断失败原因是否属「模型不可用」（用于决定是否走 on_failure 降级）。"""
    if error is None:
        return False
    text = str(error).lower()
    return any(hint in text for hint in _UNAVAILABLE_HINTS)


def translate_image(client: httpx.Client, api_key: str, path: Path, out_dir: Path, *,
                    model: str = DEFAULT_IMAGE_MODEL,
                    fallback_model: str | None = DEFAULT_IMAGE_FALLBACK_MODEL,
                    source_lang: str | None = None, target_lang: str | None = None,
                    terms=None, domain_hint: str | None = None, sensitives=None,
                    image_segment: bool = False, output_name: str | None = None,
                    min_interval_s: float | None = None, rpm: int | None = None,
                    on_event=None, cancelled=None) -> dict:
    """单图翻译主流程；主模型失败自动降级备用模型。"""
    if not path.is_file():
        raise ImageTranslateError(f"文件不存在: {path}")
    check_lang_pair(source_lang, target_lang)

    attempts = [model] + ([fallback_model] if fallback_model and fallback_model != model else [])
    last_error: Exception | None = None
    for index, current in enumerate(attempts):
        try:
            waited = throttle(current, min_interval_s, rpm)
            if on_event is not None:
                on_event({"phase": "submit", "model": current, "file": path.name,
                          "waited_s": round(waited, 1), "attempt": index + 1})
            image_url = upload_image(client, api_key, current, path)
            task_id = submit_task(client, api_key, model=current, image_url=image_url,
                                  source_lang=source_lang, target_lang=target_lang, terms=terms,
                                  domain_hint=domain_hint, sensitives=sensitives,
                                  image_segment=image_segment)
            if on_event is not None:
                on_event({"phase": "submitted", "model": current, "task_id": task_id})
            url = wait_task(client, api_key, task_id, cancelled=cancelled,
                            on_poll=(lambda status, out: on_event({"phase": "poll", "status": status,
                                                                   "task_id": task_id}))
                            if on_event is not None else None)
            suffix = Path(url.split("?")[0]).suffix or ".jpg"
            name = output_name or f"{path.stem}_译文{suffix}"
            target = download(client, url, out_dir / name)
            return {"path": str(target), "name": name, "model": current, "task_id": task_id,
                    "image_count": 1, "fallback_used": index > 0}
        except ImageTranslateError as error:
            last_error = error
            if index + 1 >= len(attempts):
                break
            if on_event is not None:
                on_event({"phase": "fallback", "from": current, "to": attempts[index + 1],
                          "reason": str(error)[:200]})
    raise ImageTranslateError(f"图片翻译失败: {last_error}")
