"""翻译引擎关键行为回归：客户端超时、思考开关（qwen-mt 例外）、并行质检。

背景：qwen-mt* 不接受 system 角色、也不接受 enable_thinking；而 qwen3.x 默认开思考，
一批 50 条会吐出上万 completion token（实测 87s/批）→ 必须显式关闭。
"""
import time
from types import SimpleNamespace

import pytest

from command_shared import llm_engine as E


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="译文"))],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
        )


class _FakeClient:
    def __init__(self):
        self.completions = _FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def _call_extra(model: str) -> dict:
    client = _FakeClient()
    E.call_chat(client, model, "SYS", "USR")
    return client.completions.kwargs.get("extra_body") or {}


def test_make_client_sets_timeout_and_retries(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(E, "OpenAI", fake_openai)
    assert E.make_client("k", "http://x") == "client"
    assert captured["timeout"] == E.DEFAULT_TIMEOUT_S
    assert captured["max_retries"] == E.DEFAULT_MAX_RETRIES


def test_call_chat_mt_has_no_thinking_flag():
    assert "enable_thinking" not in _call_extra("qwen-mt-flash")


def test_call_chat_non_mt_disables_thinking():
    assert _call_extra("qwen3.7-flash")["enable_thinking"] is False
    assert _call_extra("qwen3.7-plus")["enable_thinking"] is False


def test_call_chat_merges_into_single_user_message():
    client = _FakeClient()
    E.call_chat(client, "qwen-mt-flash", "SYS", "USR")
    msgs = client.completions.kwargs["messages"]
    assert [m["role"] for m in msgs] == ["user"]
    assert "SYS" in msgs[0]["content"] and "USR" in msgs[0]["content"]


def test_quality_batch_parallel_marks_review(monkeypatch):
    monkeypatch.setattr(E, "verify_pair", lambda src, dst: (dst == "good", "why"))
    monkeypatch.setattr(E, "ensure_quality", lambda *a, **k: ("fixed", False))
    pairs = [("a", "good"), ("b", "bad"), ("c", "good")]
    res = E._quality_batch(None, pairs, "Chinese", None, None, "fb", None, 2)
    assert res["a"] == ("good", True)
    assert res["b"] == ("fixed", False)
    assert res["c"] == ("good", True)
    assert len(res) == 3


def test_mt_batches_capped_and_others_not(monkeypatch):
    """qwen-mt* 的批必须压到 MT_BATCH_SIZE 内（多条目分隔符协议在 20 条起截断）。"""
    sizes = []

    def fake_sep(client, model, texts, source_lang, target_lang, terms=None):
        sizes.append(len(texts))
        return [f"译文{i}" for i in range(len(texts))], {}

    monkeypatch.setattr(E, "call_batch_separator", fake_sep)
    monkeypatch.setattr(E, "verify_pair", lambda src, dst: (True, ""))

    texts = [f"item {i}" for i in range(35)]

    out = E.translate_texts(None, texts, model="qwen-mt-flash", concurrency=2)
    assert sum(sizes) == 35
    assert max(sizes) <= E.MT_BATCH_SIZE
    assert len(out) == 35

    sizes.clear()
    E.translate_texts(None, texts, model="qwen3.7-flash", concurrency=2)
    assert sum(sizes) == 35
    assert max(sizes) == 35


# ---------- 限流（429 limit_requests）不得中止整条 run ----------

import httpx  # noqa: E402
from types import SimpleNamespace  # noqa: E402


def _api_error(status: int, code: str, message: str):
    req = httpx.Request("POST", "https://example.test/chat/completions")
    body = {"error": {"code": code, "message": message}}
    resp = httpx.Response(status, request=req, json=body)
    return __import__("openai").APIStatusError(message, response=resp, body=body)


def test_rate_limit_not_fatal_but_quota_is():
    assert E._is_fatal_auth(_api_error(429, "limit_requests", "You have exceeded your current request limit")) is False
    assert E._is_fatal_auth(_api_error(403, "Arrearage", "insufficient quota")) is True
    assert E._is_fatal_auth(_api_error(401, "invalid_api_key", "bad key")) is True


class _FlakyClient:
    def __init__(self, failures: int = 0, status: int = 429, code: str = "limit_requests",
                 message: str = "You have exceeded your current request limit"):
        self.failures, self.calls = failures, 0
        self._err = (status, code, message)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise _api_error(*self._err)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="译文"))], usage=None
        )


def test_call_chat_retries_on_rate_limit(monkeypatch):
    monkeypatch.setattr(E, "MT_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(E, "RATE_LIMIT_BASE_SLEEP", 0.0)
    client = _FlakyClient(failures=2)
    text, usage = E.call_chat(client, "qwen-mt-flash", "sys", "user")
    assert text == "译文"
    assert client.calls == 3


def test_call_chat_aborts_on_quota(monkeypatch):
    monkeypatch.setattr(E, "MT_MIN_INTERVAL_S", 0.0)
    with pytest.raises(E.TranslationError):
        E.call_chat(_FlakyClient(failures=99, status=403, code="Arrearage", message="insufficient quota"),
                    "qwen-mt-flash", "sys", "user")


def test_throttle_spaces_calls():
    E._last_call.clear()
    t0 = time.monotonic()
    E._throttle("k-test", 0.05)
    E._throttle("k-test", 0.05)
    assert time.monotonic() - t0 >= 0.045
