"""版式翻译渲染工具测试：overlay（原位覆盖）/ bilingual（左右分栏）/ 日期回插 / 字体回退。"""
from __future__ import annotations

import importlib
import types

import pymupdf
import pytest

from command_shared.pdf_blocks import extract_blocks, flatten_blocks

RENDER = importlib.import_module("tools.pdf.render_translated.main")


def _ctx(handle="t"):
    return types.SimpleNamespace(handle=handle)


def _pdf(path, lines):
    doc = pymupdf.open()
    page = doc.new_page()
    y = 100
    for line in lines:
        page.insert_text((72, y), line, fontsize=14)
        y += 60
    doc.save(path)
    doc.close()
    return path


def _fixture(tmp_path):
    src = _pdf(tmp_path / "src.pdf", ["AUDIT REPORT 2026", "TOTAL AMOUNT 1234 USD"])
    with pymupdf.open(src) as doc:
        blocks = extract_blocks(doc)
    items = flatten_blocks(blocks)
    translations = ["审计报告 2026", "合计金额 1234 美元"][: len(items)]
    return src, blocks, translations


def test_overlay_replaces_source_text(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    src, blocks, translations = _fixture(tmp_path)
    out = RENDER.run({"file": str(src), "blocks": blocks, "translations": translations,
                      "mode": "overlay"}, _ctx(), lambda e: None)
    assert out["mode"] == "overlay" and out["drawn"] == len(translations)
    assert out["overflow"] == 0
    text = pymupdf.open(out["path"])[0].get_text()
    assert "审计报告" in text and "合计金额" in text
    assert "AUDIT REPORT" not in text
    assert out["font"].startswith("Noto")


def test_bilingual_keeps_source_and_adds_column(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    src, blocks, translations = _fixture(tmp_path)
    out = RENDER.run({"file": str(src), "blocks": blocks, "translations": translations,
                      "mode": "bilingual", "col_width": 280}, _ctx(), lambda e: None)
    doc = pymupdf.open(out["path"])
    text = doc[0].get_text()
    assert "AUDIT REPORT" in text and "审计报告" in text
    assert doc[0].rect.width > 595 + 280
    assert out["drawn"] == len(translations)


def test_date_backfill_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    src, blocks, _ = _fixture(tmp_path)
    items = flatten_blocks(blocks)
    translations = ["报告 <D1>"] * len(items)
    out = RENDER.run({"file": str(src), "blocks": blocks, "translations": translations,
                      "index_map": list(range(len(items))),
                      "date_maps": [{"<D1>": "2026-03-01"} for _ in items],
                      "statuses": ["review"] * len(items), "mode": "overlay"},
                     _ctx(), lambda e: None)
    text = pymupdf.open(out["path"])[0].get_text()
    assert "2026-03-01" in text and "<D1>" not in text


def test_font_fallback_without_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    src, blocks, translations = _fixture(tmp_path)
    monkeypatch.setattr("command_shared.pdf_layout.cjk_font_path", lambda: None)
    out = RENDER.run({"file": str(src), "blocks": blocks, "translations": translations,
                      "mode": "overlay"}, _ctx(), lambda e: None)
    assert out["font"].startswith("china-ss")
    assert "审计报告" in pymupdf.open(out["path"])[0].get_text()


def test_rejects_missing_inputs(tmp_path, monkeypatch):
    from core.errors import ToolDomainError

    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    src, blocks, translations = _fixture(tmp_path)
    with pytest.raises(ToolDomainError):
        RENDER.run({"file": str(src), "blocks": [], "translations": translations}, _ctx(), lambda e: None)
    with pytest.raises(ToolDomainError):
        RENDER.run({"file": str(src), "blocks": blocks, "translations": []}, _ctx(), lambda e: None)
    with pytest.raises(ToolDomainError):
        RENDER.run({"file": str(src), "blocks": blocks, "translations": translations,
                    "mode": "nope"}, _ctx(), lambda e: None)
