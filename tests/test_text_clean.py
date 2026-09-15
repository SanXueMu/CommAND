"""S 批次：XML 不兼容控制字符清洗（线上 Material Specfications (2023).pdf 崩溃）。

- 单元：xml_safe_text 去除 C0/C1/NULL/孤立代理对，保留 \t\n\r 与中文
- 集成①：pymupdf 构造含控制字符文字层的 PDF → pdf.extract.pages 输出干净
- 集成②：脏文本直接进 docx 渲染（set_paragraph_text / cell / 骨架）不抛 ValueError
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod(rel: str):
    slug = rel.replace("/", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(f"_sanche.{slug}", ROOT / rel / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── 单元 ────────────────────────────────────────────────────────────────────
def test_xml_safe_strips_controls_keeps_tabs_newlines():
    from command_shared.text_clean import xml_safe_text

    dirty = "ab\x00c\x01d\x0ce\tf\ng\r中\u4e2d\x7f\x9f"
    assert xml_safe_text(dirty) == "abcde\tf\ng\r中中"
    assert xml_safe_text("") == ""
    assert xml_safe_text(None) == ""


def test_xml_safe_lone_surrogate():
    from command_shared.text_clean import xml_safe_text

    assert xml_safe_text("a\ud800b") == "ab"


# ── 集成①：extract_pages 清洗 ───────────────────────────────────────────────
def test_extract_pages_strips_control_chars(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))

    src = tmp_path / "dirty.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # 模拟损坏的 ToUnicode 映射：文字层直接带控制字符
    page.insert_text((72, 96), "He\x00llo \x01World\x0c!")
    page.insert_text((72, 130), "CleanMarker")
    doc.save(src)
    doc.close()

    tool = _mod("tools/pdf/extract_pages")
    out = tool.run({"file": str(src)}, types.SimpleNamespace(handle="h"), lambda e: None)

    joined = str(out["units"])
    assert "\x00" not in joined and "\x01" not in joined and "\x0c" not in joined
    assert "CleanMarker" in joined


# ── 集成②：docx 渲染兜底 ───────────────────────────────────────────────────
def test_docx_render_tolerates_control_chars(tmp_path):
    docx = pytest.importorskip("docx")
    from command_shared.docx_render import set_paragraph_text

    document = docx.Document()
    p = document.add_paragraph()
    set_paragraph_text(p, "干净文本")
    set_paragraph_text(p, "脏\x00文\x0c本\x01")  # 不抛 ValueError 即通过
    assert "\x00" not in p.text

    # 单元格直写路径（_write_cell 经 render_document 走 set/_write_cell；此处直接验证清洗函数一致）
    from command_shared.text_clean import xml_safe_text
    assert xml_safe_text("单\x00元\x1f格") == "单元格"


def test_ocr_parse_records_sanitizes_values():
    from command_shared.ocr_validate import parse_records

    # VL 应答里的控制字符以 \uXXXX 转义出现（JSON 合法），解析后值内含控制字符
    raw = r'[{"名称": "A\u0000B", "数量": "1\u000c"}]'
    records = parse_records(raw, ["名称", "数量"])
    assert records == [{"名称": "AB", "数量": "1"}]
