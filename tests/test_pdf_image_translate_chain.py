"""图片翻译链（pdf → 页图 → 译文页图 → 译文 PDF）本地测试。

覆盖：
- `pdf.pages.to_images`：页数/页序/文字层判定/长边收缩/子集页/格式/拦截非 PDF
- `image.batch.translate`：并发与顺序回报、单页失败不中断、全败抛错、页数上限、真实图片字节
- `pdf.from.images`：合成页数与尺寸、命名、**中间产物清理**（含 data 外路径不删）
- `images_to_pdf` 共享助手：空列表、多页顺序

LLM/DashScope 调用一律打桩（`httpx.MockTransport`），零网络。
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import fitz
import httpx
import pytest

from command_shared import image_translate as it
from tools.image.batch_translate import main as batch_main
from tools.pdf.from_images import main as from_images_main
from tools.pdf.pages_to_images import main as to_images_main


# ---------------------------------------------------------------- 测试脚手架

class Ctx:
    def __init__(self, handle: str = "h_test", keys: dict | None = None):
        self.handle = handle
        self.keys = keys if keys is not None else {
            "k1": {"api_key": "sk-test", "is_default": True, "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}
        }
        self.cancel_event = None


def events():
    collected: list[dict] = []
    return collected, collected.append


@contextmanager
def data_root(tmp_path: Path):
    prev = os.environ.get("COMMAND_DATA_DIR")
    os.environ["COMMAND_DATA_DIR"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        if prev is None:
            os.environ.pop("COMMAND_DATA_DIR", None)
        else:
            os.environ["COMMAND_DATA_DIR"] = prev


def make_pdf(path: Path, pages: int = 3, text: bool = True) -> Path:
    """造多页 PDF：text=False 为纯图页（模拟扫描件）。"""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200 + i * 10, height=300)
        if text:
            page.insert_text((20, 40), f"Page {i + 1} contract text")
        else:
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60 + i, 40), False)
            pix.set_rect(pix.irect, (200, 30, 30))
            page.insert_image(fitz.Rect(20, 60, 120, 140), pixmap=pix)
    doc.save(path)
    doc.close()
    return path


def make_png(path: Path, width: int = 80, height: int = 120, color: tuple = (10, 120, 200)) -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pix.set_rect(pix.irect, color)
    pix.save(path)
    return path


@pytest.fixture(autouse=True)
def _fast_throttle(monkeypatch):
    monkeypatch.setattr(it, "DEFAULT_RPM", 0)
    it._last_submit.clear()


# ------------------------------------------------------------ DashScope 打桩

def dashscope_handler(requests: list[dict], *, fail_urls: set[str] | None = None):
    """最小可用的 DashScope 异步图片翻译服务：getPolicy → OSS → 提交 → 轮询 → 下载。"""
    fail_urls = fail_urls or set()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = request.content
        requests.append({"method": request.method, "url": url, "body": body})
        if url.endswith("/api/v1/uploads") or "action=getPolicy" in url:
            return httpx.Response(200, json={"data": {
                "policy": "cG9s", "signature": "c2ln", "upload_dir": "dashscope/dir",
                "upload_host": "https://oss.example.com", "expire_in_seconds": 300,
            }})
        if url.startswith("https://oss.example.com"):
            return httpx.Response(200)
        if url.endswith("/image-synthesis"):
            payload = json.loads(body)
            src = payload["input"]["image_url"]
            return httpx.Response(200, json={"output": {"task_id": f"task-{Path(src).name}"}})
        if "/api/v1/tasks/" in url:
            task_id = url.rsplit("/", 1)[-1]
            name = task_id.replace("task-", "")
            if name in fail_urls:
                return httpx.Response(200, json={"output": {"task_status": "FAILED", "message": "bad image"}})
            return httpx.Response(200, json={"output": {
                "task_status": "SUCCEEDED", "results": [{"url": f"https://cdn.example.com/{name}"}]}})
        if url.startswith("https://cdn.example.com"):
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nFAKE-TRANSLATED")
        return httpx.Response(404, json={"message": f"unexpected {url}"})

    return handler


@contextmanager
def stub_dashscope(requests: list[dict], *, fail_urls: set[str] | None = None):
    transport = httpx.MockTransport(dashscope_handler(requests, fail_urls=fail_urls))
    original = it.make_client

    def patched(base_url=None):
        return httpx.Client(transport=transport, base_url=it.native_base(base_url), timeout=5.0)

    it.make_client = patched
    try:
        yield
    finally:
        it.make_client = original


# ------------------------------------------------------- pdf.pages.to_images

def test_pages_to_images_renders_in_order_and_reports_text_layer(tmp_path):
    with data_root(tmp_path):
        src = make_pdf(tmp_path / "文字版.pdf", pages=3, text=True)
        out = to_images_main.run({"file": str(src)}, Ctx(), events()[1])
        assert out["page_count"] == 3 and out["rendered"] == 3
        assert out["has_text_layer"] is True
        assert [Path(p).name for p in out["paths"]] == ["page_0001.jpg", "page_0002.jpg", "page_0003.jpg"]
        assert all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in out["paths"])
        assert out["images"][1]["page"] == 2 and out["images"][1]["width"] > 0


def test_pages_to_images_scanned_pdf_is_flagged(tmp_path):
    with data_root(tmp_path):
        src = make_pdf(tmp_path / "扫描件.pdf", pages=2, text=False)
        out = to_images_main.run({"file": str(src)}, Ctx(), events()[1])
        assert out["has_text_layer"] is False and out["rendered"] == 2


def test_pages_to_images_subset_format_and_max_side(tmp_path):
    with data_root(tmp_path):
        src = make_pdf(tmp_path / "大图.pdf", pages=3, text=True)
        out = to_images_main.run(
            {"file": str(src), "pages": [1, 3], "format": "png", "max_side": 100}, Ctx(), events()[1])
        assert [Path(p).name for p in out["paths"]] == ["page_0001.png", "page_0003.png"]
        assert out["effective_scale"] < out["scale"]          # 长边上限触发降采样
        assert out["images"][0]["width"] <= 100


def test_pages_to_images_rejects_non_pdf(tmp_path):
    with data_root(tmp_path):
        other = tmp_path / "a.txt"
        other.write_text("x", encoding="utf-8")
        with pytest.raises(Exception) as error:
            to_images_main.run({"file": str(other)}, Ctx(), events()[1])
        assert "仅支持 PDF" in str(error.value)


# ------------------------------------------------- image.batch.translate

def test_batch_translates_all_pages_with_progress(tmp_path):
    with data_root(tmp_path):
        images = [make_png(tmp_path / f"p{i}.png") for i in range(1, 4)]
        requests: list[dict] = []
        seen, emit = events()
        with stub_dashscope(requests):
            out = batch_main.run({"images": [str(p) for p in images], "target_lang": "Chinese"}, Ctx(), emit)
        assert out["count"] == 3 and out["ok_count"] == 3 and out["failed"] == 0
        assert out["usage"]["image_count"] == 3
        assert [Path(p).name for p in out["paths"]] == ["p1_译文.png", "p2_译文.png", "p3_译文.png"]
        assert [i["index"] for i in out["images"]] == [1, 2, 3]        # 顺序与入参一致
        assert all(Path(p).read_bytes().startswith(b"\x89PNG") for p in out["paths"])
        assert [e["phase"] for e in seen].count("translated") == 3
        submits = [r for r in requests if str(r["url"]).endswith("/image-synthesis")]
        assert len(submits) == 3
        assert json.loads(submits[0]["body"])["model"] == "qwen-mt-image-2.0"


def test_batch_single_page_failure_does_not_abort(tmp_path):
    with data_root(tmp_path):
        images = [make_png(tmp_path / f"q{i}.png") for i in range(1, 4)]
        seen, emit = events()
        with stub_dashscope([], fail_urls={"q2.png"}):
            out = batch_main.run({"images": [str(p) for p in images], "target_lang": "Chinese"}, Ctx(), emit)
        assert out["ok_count"] == 2 and out["failed"] == 1
        failed = [i for i in out["images"] if not i["ok"]]
        assert failed[0]["index"] == 2 and "bad image" in failed[0]["error"]
        assert [i for i in seen if i["phase"] == "page_failed"][0]["page"] == 2


def test_batch_all_failed_raises_with_reasons(tmp_path):
    with data_root(tmp_path):
        images = [make_png(tmp_path / "z1.png"), make_png(tmp_path / "z2.png")]
        with stub_dashscope([], fail_urls={"z1.png", "z2.png"}):
            with pytest.raises(Exception) as error:
                batch_main.run({"images": [str(p) for p in images], "target_lang": "Chinese"}, Ctx(), events()[1])
        assert "全部 2 页翻译失败" in str(error.value)


def test_batch_rejects_over_queue_max(tmp_path, monkeypatch):
    with data_root(tmp_path):
        first = make_png(tmp_path / "one.png")
        monkeypatch.setattr(it, "QUEUE_MAX", 3)
        with pytest.raises(Exception) as error:
            batch_main.run({"images": [str(first)] * 4}, Ctx(), events()[1])
        assert "超过图片翻译单任务上限" in str(error.value) and "请拆分" in str(error.value)


def test_batch_passes_terms_and_fallback(tmp_path):
    with data_root(tmp_path):
        image = make_png(tmp_path / "t1.png")
        requests: list[dict] = []
        with stub_dashscope(requests):
            batch_main.run({
                "images": [str(image)], "target_lang": "Chinese",
                "terms": [["Audit", "审计"]], "domain_hint": "审计财务",
                "fallback_model": "qwen-mt-image",
            }, Ctx(), events()[1])
        payload = json.loads([r for r in requests if str(r["url"]).endswith("/image-synthesis")][0]["body"])
        assert payload["input"]["ext"]["terminologies"] == [{"src": "Audit", "tgt": "审计"}]
        assert payload["input"]["ext"]["domainHint"] == "审计财务"


def test_batch_requires_keys(tmp_path):
    with data_root(tmp_path):
        image = make_png(tmp_path / "nk.png")
        with pytest.raises(Exception) as error:
            batch_main.run({"images": [str(image)]}, Ctx(keys={}), events()[1])
        assert "无可用密钥" in str(error.value)


# --------------------------------------------------------- pdf.from.images

def test_from_images_composes_and_cleans_intermediates(tmp_path):
    with data_root(tmp_path):
        pages_dir = tmp_path / "outputs" / "h_test" / "tmp_pages"
        translated_dir = tmp_path / "outputs" / "h_test" / "tmp_mt_images"
        pages_dir.mkdir(parents=True)
        translated_dir.mkdir(parents=True)
        page_paths = [make_png(pages_dir / f"page_{i:04d}.jpg") for i in (1, 2)]
        translated = [make_png(translated_dir / f"page_{i:04d}_zh.jpg", width=90, height=140) for i in (1, 2)]
        src = make_pdf(tmp_path / "合同.pdf", pages=2)

        seen, emit = events()
        out = from_images_main.run({
            "images": [str(p) for p in translated], "source_file": str(src),
            "cleanup_dirs": [str(pages_dir), str(translated_dir)],
        }, Ctx(), emit)
        assert out["name"] == "合同_图片译文.pdf" and out["pages"] == 2
        dest = Path(out["path"])
        assert dest.is_file() and dest.stat().st_size > 0
        with fitz.open(dest) as doc:                     # 页尺寸跟随图片
            assert doc.page_count == 2
            assert round(doc[0].rect.width) == 90 and round(doc[0].rect.height) == 140
        assert not pages_dir.exists() and not translated_dir.exists()   # 中间产物已清理
        assert out["cleanup"]["files_removed"] == 4 and out["cleanup"]["bytes_freed"] > 0
        assert [i for i in seen if i["phase"] == "composed"][0]["pages"] == 2


def test_from_images_keeps_paths_outside_data_dir(tmp_path):
    with data_root(tmp_path):
        data_dir = tmp_path
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        keep = make_png(outside / "keep.png")
        safe = data_dir / "outputs" / "h_test" / "tmp_x"
        safe.mkdir(parents=True)
        image = make_png(safe / "a.png")

        out = from_images_main.run({"images": [str(image)], "cleanup_dirs": [str(outside)]}, Ctx(), events()[1])
        assert keep.is_file()                                     # data 目录外不删
        assert str(outside) in out["cleanup"]["skipped"]
        assert Path(out["path"]).is_file()


def test_from_images_rejects_empty_and_missing(tmp_path):
    with data_root(tmp_path):
        with pytest.raises(Exception):
            from_images_main.run({"images": []}, Ctx(), events()[1])
        with pytest.raises(Exception) as error:
            from_images_main.run({"images": [str(tmp_path / "nope.png")]}, Ctx(), events()[1])
        assert "译文图片不存在" in str(error.value)
