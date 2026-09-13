"""pdf.extract.blocks / pdf.blocks.to_segments / command_shared.pdf_blocks 测试。"""
from __future__ import annotations

import importlib
import types
from pathlib import Path

import pytest

from command_shared import pdf_ocr
from command_shared.pdf_blocks import extract_blocks, flatten_blocks


def _blocks_tool():
    return importlib.import_module("tools.pdf.extract_blocks.main")


def _to_segments_tool():
    return importlib.import_module("tools.pdf.blocks_to_segments.main")


def _paragraphs_pdf(path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "AUDIT REPORT 2026", fontsize=16)
    page.insert_text((72, 300), "TOTAL AMOUNT 1234 USD", fontsize=16)
    doc.save(path)
    doc.close()
    return path


def _table_pdf(path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    x0, y0, w, h = 72, 72, 200, 40
    for r in range(3):
        page.draw_line((x0, y0 + r * h), (x0 + 2 * w, y0 + r * h))
    for c in range(3):
        page.draw_line((x0 + c * w, y0), (x0 + c * w, y0 + 2 * h))
    cells = [["Name", "Amount"], ["Total", "1234"]]
    for r in range(2):
        for c in range(2):
            page.insert_text((x0 + c * w + 6, y0 + r * h + 24), cells[r][c], fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _image_pdf(path: Path, text: str = "INVOICE TOTAL 1234 USD") -> Path:
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


# ── 块提取 ───────────────────────────────────────────────────────────────────
def test_text_blocks_have_bbox_and_order(tmp_path):
    import pymupdf

    src = _paragraphs_pdf(tmp_path / "p.pdf")
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc)
    texts = [b["text"] for b in blocks if b["type"] == "text"]
    assert any("AUDIT REPORT" in t for t in texts)
    assert any("TOTAL AMOUNT" in t for t in texts)
    for b in blocks:
        assert b["page"] == 1 and b["id"].startswith("1.")
        assert len(b["bbox"]) == 4
    # 阅读顺序：上方块在前
    assert texts[0].startswith("AUDIT")


def test_table_block_extracted_with_cells(tmp_path):
    import pymupdf

    src = _table_pdf(tmp_path / "t.pdf")
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc)
    tables = [b for b in blocks if b["type"] == "table"]
    assert tables, "应识别到表格块"
    cells = tables[0]["cells"]
    joined = " ".join(c["text"] for c in cells)
    assert "Name" in joined and "1234" in joined
    assert all(len(c["bbox"]) == 4 for c in cells)


def test_include_tables_false(tmp_path):
    import pymupdf

    src = _table_pdf(tmp_path / "t.pdf")
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc, include_tables=False)
    assert not [b for b in blocks if b["type"] == "table"]


def test_flatten_text_and_cells(tmp_path):
    import pymupdf

    src = _table_pdf(tmp_path / "t.pdf")
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc)
    items = flatten_blocks(blocks)
    assert items and all(it["index"] == i for i, it in enumerate(items))
    kinds = {it["kind"] for it in items}
    assert "cell" in kinds
    assert all(len(it["bbox"]) == 4 for it in items)


# ── 工具接线 ─────────────────────────────────────────────────────────────────
def test_extract_blocks_tool_run(tmp_path):
    src = _paragraphs_pdf(tmp_path / "p.pdf")
    out = _blocks_tool().run({"file": str(src)}, types.SimpleNamespace(handle="h"), lambda e: None)
    assert out["kind"] == "pdf_blocks"
    assert out["pages"] == 1
    assert out["blocks"]


def test_blocks_to_segments_tool_run(tmp_path):
    import pymupdf

    src = _paragraphs_pdf(tmp_path / "p.pdf")
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc)
    out = _to_segments_tool().run({"blocks": blocks}, types.SimpleNamespace(handle="h"), lambda e: None)
    assert out["segments"] and len(out["refs"]) == len(out["segments"])
    assert any("AUDIT" in s for s in out["segments"])


def test_blocks_to_segments_rejects_empty():
    from core.errors import ToolDomainError

    with pytest.raises(ToolDomainError, match="blocks 为空"):
        _to_segments_tool().run({"blocks": []}, types.SimpleNamespace(handle="h"), lambda e: None)


def test_extract_blocks_auto_ocr_applies(monkeypatch, tmp_path):
    src = _image_pdf(tmp_path / "scan.pdf")
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))

    def fake_add(s, d, **kwargs):  # noqa: ARG001
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        _paragraphs_pdf(Path(d))
        return {"path": str(d), "pages": 1, "pages_ocr": 1, "applied": True, "languages": "eng"}

    monkeypatch.setattr(pdf_ocr, "add_ocr_layer", fake_add)
    out = _blocks_tool().run({"file": str(src), "auto_ocr": True},
                             types.SimpleNamespace(handle="h-ocr"), lambda e: None)
    assert out["ocr_applied"] is True
    texts = " ".join(b.get("text", "") for b in out["blocks"])
    assert "AUDIT REPORT" in texts


@pytest.mark.skipif(not pdf_ocr.ocrmypdf_available(), reason="本机无 ocrmypdf，跳过真实 OCR")
def test_extract_blocks_real_scanned(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path / "data"))
    src = _image_pdf(tmp_path / "scan.pdf", text="INVOICE TOTAL 1234 USD")
    out = _blocks_tool().run({"file": str(src), "auto_ocr": True, "ocr_languages": "eng"},
                             types.SimpleNamespace(handle="real-blocks"), lambda e: None)
    assert out["ocr_applied"] is True
    text = " ".join(b.get("text", "") for b in out["blocks"]).upper()
    assert "INVOICE" in text
