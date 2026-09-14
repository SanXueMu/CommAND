"""文件探测端点测试：GET /files/probe（只读，判定扫描件/文字版 → 工作台自动选流）。

零外部依赖：PDF 用 pymupdf 现场造（一页有文字 / 一页纯图），图片只放空文件。
"""

import io
import zipfile  # noqa: F401  （与同目录测试保持一致的依赖面）
from pathlib import Path

import fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import deps
from config import Config


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from api import files_router

    stub = Config(
        host="127.0.0.1", port=0, database_url="postgresql://x/x", worker_concurrency=1,
        heartbeat_interval_s=15, heartbeat_timeout_s=90,
        tools_dir=tmp_path, data_dir=tmp_path,
    )
    monkeypatch.setattr(deps, "get_config", lambda: stub)
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    with TestClient(app) as c:
        yield c, tmp_path


def _text_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Audited Financial Statements page {i + 1} " * 4)
    doc.save(path)
    doc.close()


def _scanned_pdf(path: Path, pages: int = 3) -> None:
    """无文字层：只放一张图（模拟扫描件）。"""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_image(fitz.Rect(50, 50, 300, 300), stream=_png_bytes())
    doc.save(path)
    doc.close()


def _png_bytes() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60))
    pix.set_rect(pix.irect, (240, 240, 240))
    return pix.tobytes("png")


def test_probe_scanned_pdf_is_image_kind(client):
    c, tmp_path = client
    target = tmp_path / "扫描件.pdf"
    _scanned_pdf(target, pages=3)

    body = c.get("/api/files/probe", params={"path": str(target)}).json()

    assert body["kind"] == "pdf" and body["pages"] == 3
    assert body["has_text_layer"] is False, "无文字层 = 扫描件（应自动走图片流）"
    assert body["image_max_pages"] == 500


def test_probe_text_pdf_has_text_layer(client):
    c, tmp_path = client
    target = tmp_path / "文字版.pdf"
    _text_pdf(target, pages=2)

    body = c.get("/api/files/probe", params={"path": str(target)}).json()

    assert body["kind"] == "pdf" and body["pages"] == 2
    assert body["has_text_layer"] is True, "有文字层 = 走文字链路"


def test_probe_image_and_other_kinds(client):
    c, tmp_path = client
    img = tmp_path / "扫描图.png"
    img.write_bytes(_png_bytes())
    doc = tmp_path / "报告.docx"
    doc.write_bytes(b"PK\x03\x04docx")

    assert c.get("/api/files/probe", params={"path": str(img)}).json()["kind"] == "image"
    other = c.get("/api/files/probe", params={"path": str(doc)}).json()
    assert other["kind"] == "document" and other["pages"] is None and other["has_text_layer"] is None


def test_probe_rejects_outside_data_dir_and_missing_file(client):
    c, tmp_path = client
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4")

    assert c.get("/api/files/probe", params={"path": str(outside)}).status_code == 403
    assert c.get("/api/files/probe", params={"path": str(tmp_path / "无.pdf")}).status_code == 404
