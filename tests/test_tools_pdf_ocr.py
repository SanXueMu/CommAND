"""pdf.ocr.addlayer / command_shared.pdf_ocr 测试：检测 + 补层 + 工具接线。"""
from __future__ import annotations

import importlib
import os
import types
from pathlib import Path

import pytest

from command_shared import pdf_ocr


# ── 造样本 PDF ────────────────────────────────────────────────────────────────
def _text_pdf(path: Path, text: str = "INVOICE TOTAL 1234 USD") -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=20)
    doc.save(path)
    doc.close()
    return path


def _image_pdf(path: Path, text: str = "INVOICE TOTAL 1234 USD") -> Path:
    """把文字渲染成图，做成「无文字层」的扫描件。"""
    import pymupdf

    tmp = pymupdf.open()
    p = tmp.new_page()
    p.insert_text((72, 120), text, fontsize=28)
    pix = p.get_pixmap(dpi=200)
    img = pix.tobytes("png")
    tmp.close()

    doc = pymupdf.open()
    page = doc.new_page(width=pix.width * 72 / 200, height=pix.height * 72 / 200)
    page.insert_image(page.rect, stream=img)
    doc.save(path)
    doc.close()
    return path


# ── 检测 ─────────────────────────────────────────────────────────────────────
def test_text_pdf_needs_no_ocr(tmp_path):
    src = _text_pdf(tmp_path / "text.pdf")
    assert pdf_ocr.needs_ocr(src) is False
    assert pdf_ocr.scanned_pages(src) == []


def test_image_pdf_detected_as_scanned(tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    assert pdf_ocr.page_count(src) == 1
    assert pdf_ocr.needs_ocr(src) is True
    assert pdf_ocr.scanned_pages(src) == [1]


def test_add_layer_noop_when_text_present(tmp_path):
    src = _text_pdf(tmp_path / "text.pdf")
    out = tmp_path / "out.pdf"
    result = pdf_ocr.add_ocr_layer(src, out)
    assert result["applied"] is False
    assert result["path"] == str(src)
    assert not out.exists()


def test_add_layer_rejects_over_max_pages(tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    from core.errors import ToolDomainError

    with pytest.raises(ToolDomainError, match="超过上限"):
        pdf_ocr.add_ocr_layer(src, tmp_path / "o.pdf", max_pages=0)


def test_add_layer_missing_ocrmypdf(monkeypatch, tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(pdf_ocr, "ocrmypdf_available", lambda: False)
    from core.errors import ToolDomainError

    with pytest.raises(ToolDomainError, match="ocrmypdf"):
        pdf_ocr.add_ocr_layer(src, tmp_path / "o.pdf")


def test_add_layer_builds_expected_command(monkeypatch, tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    dst = tmp_path / "out" / "o.pdf"
    monkeypatch.setattr(pdf_ocr, "ocrmypdf_available", lambda: True)
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text, timeout):  # noqa: ARG001
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        Path(cmd[-1]).write_bytes(b"%PDF-1.4 fake")
        return _Proc()

    monkeypatch.setattr(pdf_ocr.subprocess, "run", fake_run)
    result = pdf_ocr.add_ocr_layer(src, dst, jobs=2, oversample=300, force=True, timeout_s=123)

    cmd = captured["cmd"]
    assert cmd[0] == "ocrmypdf"
    assert "-l" in cmd and "eng+chi_sim" in cmd
    assert "--force-ocr" in cmd and "--skip-text" not in cmd
    assert cmd[cmd.index("--jobs") + 1] == "2"
    assert cmd[cmd.index("--oversample") + 1] == "300"
    assert cmd[-2] == str(src) and cmd[-1] == str(dst)
    assert captured["timeout"] == 123
    assert result["applied"] is True and result["pages_ocr"] == 1


def test_add_layer_skip_text_flag_by_default(monkeypatch, tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(pdf_ocr, "ocrmypdf_available", lambda: True)
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text, timeout):  # noqa: ARG001
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"%PDF-1.4 fake")
        return _Proc()

    monkeypatch.setattr(pdf_ocr.subprocess, "run", fake_run)
    pdf_ocr.add_ocr_layer(src, tmp_path / "o.pdf")
    assert "--skip-text" in captured["cmd"]
    assert "--force-ocr" not in captured["cmd"]


def test_ocrmypdf_failure_raises(monkeypatch, tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(pdf_ocr, "ocrmypdf_available", lambda: True)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "some ocr error"

    monkeypatch.setattr(pdf_ocr.subprocess, "run",
                        lambda *a, **k: _Proc())
    from core.errors import ToolDomainError

    with pytest.raises(ToolDomainError, match="OCRmyPDF 执行失败"):
        pdf_ocr.add_ocr_layer(src, tmp_path / "o.pdf")


# ── 工具接线 ─────────────────────────────────────────────────────────────────
def test_tool_run_writes_output_dir(monkeypatch, tmp_path):
    tool_main = importlib.import_module("tools.pdf.ocr_addlayer.main")
    src = _image_pdf(tmp_path / "扫描件.pdf")
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))

    def fake_add(s, d, **kwargs):  # noqa: ARG001
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        Path(d).write_bytes(b"%PDF-1.4 layered")
        return {"path": str(d), "pages": 1, "pages_ocr": 1, "applied": True,
                "languages": "eng+chi_sim"}

    monkeypatch.setattr(tool_main, "add_ocr_layer", fake_add)
    ctx = types.SimpleNamespace(handle="h-1", attempt=1)
    out = tool_main.run({"file": str(src)}, ctx, lambda e: None)

    assert out["applied"] is True and out["pages_ocr"] == 1
    assert out["file"].endswith("扫描件_可搜索.pdf")
    assert Path(out["file"]).is_file()
    assert (tmp_path / "data" / "outputs" / "h-1").is_dir()


# ── 真实 OCR 集成（缺 ocrmypdf 时跳过）───────────────────────────────────────
@pytest.mark.skipif(not pdf_ocr.ocrmypdf_available(), reason="本机无 ocrmypdf，跳过真实 OCR")
def test_real_ocr_produces_searchable_text(tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf", text="INVOICE TOTAL 1234 USD")
    out = tmp_path / "searchable.pdf"
    result = pdf_ocr.add_ocr_layer(src, out, languages="eng", jobs=1, clean=False)
    assert result["applied"] is True

    import pymupdf

    with pymupdf.open(out) as doc:
        text = doc[0].get_text().upper()
    assert "INVOICE" in text
    assert "1234" in text
