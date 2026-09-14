"""image.mt.translate 图片翻译：纯逻辑 + MockTransport 全流程（零网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from command_shared import image_translate as it
from command_shared.glossary import as_terminologies, parse_terms

BASE = "https://dashscope.aliyuncs.com"
# 导入时的原始常量（autouse fixture 会把 DEFAULT_RPM 临时置 0，这里守恒断言用原始值）
SOURCE_LIMITS = (it.DEFAULT_RPM, it.DEFAULT_CONCURRENCY, it.QUEUE_MAX)


@pytest.fixture(autouse=True)
def _fast_throttle(monkeypatch):
    """测试不真等 60s：把 RPM=1 模型表清空（限速逻辑由专门用例显式验证）。"""
    monkeypatch.setattr(it, "DEFAULT_RPM", 0)
    it._last_submit.clear()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE, timeout=5.0)


class _FakeCtx:
    handle = "h_test"
    attempt = 1
    cancel_event = None
    keys = {"dashscope": {"api_key": "sk-test", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                          "is_default": True}}

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


# ---------------------------------------------------------------- 工具函数

def test_native_base_strips_compatible_suffix():
    assert it.native_base("https://dashscope.aliyuncs.com/compatible-mode/v1") == BASE
    assert it.native_base("https://dashscope.aliyuncs.com/") == BASE
    assert it.native_base("") == it.DEFAULT_BASE
    assert it.native_base(None) == it.DEFAULT_BASE
    assert it.native_base("http://gw.local:9000/v1") == "http://gw.local:9000"


def test_lang_code_mapping_and_passthrough():
    assert it.lang_code("中文") == "zh" and it.lang_code("English") == "en"
    assert it.lang_code("Japanese") == "ja" and it.lang_code("") is None
    assert it.lang_code("Klingon") == "Klingon"


def test_check_lang_pair_requires_zh_or_en():
    it.check_lang_pair("English", "Japanese")   # 含 en ✓
    it.check_lang_pair("auto", "Japanese")      # 自动识别 ✓
    it.check_lang_pair(None, "Chinese")         # 目标中文 ✓
    with pytest.raises(it.ImageTranslateError, match="至少一方为中文/英文"):
        it.check_lang_pair("Japanese", "Korean")


def test_throttle_respects_min_interval(monkeypatch):
    it._last_submit.clear()
    calls = {"sleep": 0.0}
    monkeypatch.setattr(it.time, "sleep", lambda s: calls.__setitem__("sleep", calls["sleep"] + s))
    assert it.throttle("qwen-mt-image-2.0", min_interval_s=0) == 0.0
    it.throttle("qwen-mt-image-2.0", min_interval_s=30)
    assert it.throttle("qwen-mt-image-2.0", min_interval_s=30) > 0  # 第二次触发等待
    assert calls["sleep"] > 0


def test_throttle_derives_interval_from_rpm(monkeypatch):
    """RPM 推导间隔：60 rpm → 1s；120 rpm → 0.5s；0/负数 → 不限速。"""
    it._last_submit.clear()
    slept: list[float] = []
    monkeypatch.setattr(it.time, "sleep", lambda s: slept.append(s))
    assert it.throttle("m", rpm=0) == 0.0 and not slept
    it.throttle("m", rpm=60)          # 首次不等待
    waited = it.throttle("m", rpm=60)  # 第二次：间隔 1s（实测已过 0.0s+）
    assert 0.0 < waited <= 1.0
    it._last_submit.clear()
    it.throttle("m2", rpm=120)
    assert 0.0 < it.throttle("m2", rpm=120) <= 0.5


def test_default_rpm_matches_platform_limit():
    """默认限速对齐通义千问平台 qwen-mt-image-2.0：RPM 60 / 并发 2 / 队列 500。"""
    assert SOURCE_LIMITS == (60, 2, 500)


def test_glossary_accepts_list_and_text():
    assert parse_terms("a => b\n# c\n\nd -> e") == [("a", "b"), ("d", "e")]
    assert parse_terms([["净值", "NAV"], {"src": "审计", "tgt": "audit"}, ["", "x"]]) == \
        [("净值", "NAV"), ("审计", "audit")]
    assert as_terminologies([["净值", "NAV"]]) == [{"src": "净值", "tgt": "NAV"}]


# ---------------------------------------------------------------- 全流程

def _handler(state: dict, *, fail_models: set[str] | None = None, task_status="SUCCEEDED"):  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/uploads" in url:
            return httpx.Response(200, json={"data": {
                "upload_host": f"{BASE}/oss-upload", "upload_dir": "dashscope/dir",
                "policy": "p", "oss_access_key_id": "ak", "signature": "sig",
                "x_oss_object_acl": "private", "x_oss_forbid_overwrite": "true"}})
        if url.endswith("/oss-upload"):
            return httpx.Response(200)
        if "image-synthesis" in url:
            body = json.loads(request.content)
            state.setdefault("submitted", []).append(body)
            if body["model"] in (fail_models or set()):
                return httpx.Response(400, json={"code": "InvalidParameter", "message": "model not available"})
            return httpx.Response(200, json={"output": {"task_id": f"t_{body['model']}"}})
        if "/api/v1/tasks/" in url:
            state["polls"] = state.get("polls", 0) + 1
            status = "RUNNING" if state["polls"] < 2 and task_status == "SUCCEEDED" else task_status
            output = {"task_status": status}
            if status == "SUCCEEDED":
                output["results"] = [{"url": f"{BASE}/result/out.jpg"}]
            if status == "FAILED":
                output["message"] = "boom"
            return httpx.Response(200, json={"output": output})
        if url.endswith("/result/out.jpg"):
            return httpx.Response(200, content=b"JPEGDATA")
        raise AssertionError(f"未预期的请求: {url}")

    return handler


def _img(tmp_path: Path) -> Path:
    p = tmp_path / "扫描件.png"
    p.write_bytes(b"PNG")
    return p


def test_translate_image_happy_path(tmp_path):
    state: dict = {}
    events: list[dict] = []
    out = tmp_path / "out"
    with _client(_handler(state)) as client:
        result = it.translate_image(
            client, "sk-test", _img(tmp_path), out,
            source_lang="English", target_lang="Chinese",
            terms=[["净值", "NAV"]], domain_hint="finance",
            on_event=events.append)
    assert result["model"] == it.DEFAULT_IMAGE_MODEL and result["fallback_used"] is False
    assert result["image_count"] == 1 and result["name"].endswith("_译文.jpg")
    assert (out / result["name"]).read_bytes() == b"JPEGDATA"
    payload = state["submitted"][0]
    assert payload["input"]["target_lang"] == "zh" and payload["input"]["source_lang"] == "en"
    assert payload["input"]["ext"]["terminologies"] == [{"src": "净值", "tgt": "NAV"}]
    assert payload["input"]["ext"]["domainHint"] == "finance"
    assert [e["phase"] for e in events][:2] == ["submit", "submitted"]
    assert any(e.get("phase") == "poll" for e in events)


def test_translate_image_falls_back_to_secondary_model(tmp_path):
    state: dict = {}
    events: list[dict] = []
    with _client(_handler(state, fail_models={it.DEFAULT_IMAGE_MODEL})) as client:
        result = it.translate_image(client, "sk-test", _img(tmp_path), tmp_path / "out",
                                    on_event=events.append)
    assert result["fallback_used"] is True and result["model"] == it.DEFAULT_IMAGE_FALLBACK_MODEL
    assert [m["model"] for m in state["submitted"]] == [it.DEFAULT_IMAGE_MODEL, it.DEFAULT_IMAGE_FALLBACK_MODEL]
    fallback = [e for e in events if e.get("phase") == "fallback"]
    assert fallback and "model not available" in fallback[0]["reason"]


def test_translate_image_raises_when_all_models_fail(tmp_path):
    state: dict = {}
    with _client(_handler(state, fail_models={it.DEFAULT_IMAGE_MODEL, it.DEFAULT_IMAGE_FALLBACK_MODEL})) as client:
        with pytest.raises(it.ImageTranslateError, match="图片翻译失败"):
            it.translate_image(client, "sk-test", _img(tmp_path), tmp_path / "out")


def test_translate_image_task_failed(tmp_path):
    with _client(_handler({}, task_status="FAILED")) as client:
        with pytest.raises(it.ImageTranslateError, match="FAILED"):
            it.translate_image(client, "sk-test", _img(tmp_path), tmp_path / "out",
                               fallback_model=None)


def test_translate_image_missing_file(tmp_path):
    with _client(_handler({})) as client:
        with pytest.raises(it.ImageTranslateError, match="文件不存在"):
            it.translate_image(client, "sk-test", tmp_path / "nope.png", tmp_path / "out")


# ---------------------------------------------------------------- 工具层

def test_tool_run_writes_product_and_reports_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))
    state: dict = {}
    ctx = _FakeCtx()
    monkeypatch.setattr(it, "make_client", lambda base_url=None, timeout=it.TIMEOUT_S: _client(_handler(state)))

    from importlib import import_module
    tool = import_module("tools.image.mt_translate.main")
    out = tool.run({"file": str(_img(tmp_path)), "target_lang": "Chinese"}, ctx, ctx.emit)

    assert Path(out["path"]).is_file() and out["path"].endswith("h_test") is False
    assert str(tmp_path / "data" / "outputs" / "h_test") in out["path"]
    assert out["source_file"].endswith("扫描件.png") and out["image_count"] == 1
    assert out["model"] == it.DEFAULT_IMAGE_MODEL and out["fallback_used"] is False
    assert any(e.get("phase") == "translated" for e in ctx.events)


def test_tool_run_without_keys_reports_domain_error(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))
    ctx = _FakeCtx()
    ctx.keys = {}
    from importlib import import_module
    from core.errors import ToolDomainError
    tool = import_module("tools.image.mt_translate.main")
    with pytest.raises(ToolDomainError, match="APIKey管理"):
        tool.run({"file": str(_img(tmp_path))}, ctx, ctx.emit)


def test_tool_defaults_fallback_model_when_key_absent(tmp_path, monkeypatch):
    """入参不带 fallback_model（flow 模板没传）时，必须回落到默认备用模型——
    否则显式 None 会吃掉默认值，主模型不可用时就没有「走远方案」（2026-09-14 复盘）。"""
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))
    state: dict = {}
    ctx = _FakeCtx()
    monkeypatch.setattr(it, "make_client",
                        lambda base_url=None, timeout=it.TIMEOUT_S: _client(_handler(state, fail_models={it.DEFAULT_IMAGE_MODEL})))

    from importlib import import_module
    tool = import_module("tools.image.mt_translate.main")
    out = tool.run({"file": str(_img(tmp_path)), "target_lang": "Chinese"}, ctx, ctx.emit)

    submitted = [b["model"] for b in state.get("submitted", [])]
    assert submitted == [it.DEFAULT_IMAGE_MODEL, it.DEFAULT_IMAGE_FALLBACK_MODEL], submitted
    assert out["model"] == it.DEFAULT_IMAGE_FALLBACK_MODEL
    assert out["fallback_used"] is True
