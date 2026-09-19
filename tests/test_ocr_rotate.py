"""V2 自动旋转测试：tesseract OSD 方向检测 + 渲染回正 + ocrmypdf --rotate-pages。

无 tesseract（或无 osd 数据）的环境自动跳过——功能本身在那类环境退化为「不旋转」。
"""
from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from command_shared.ocr_render import detect_orientation_osd, render_page

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _tesseract_ready() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                              text=True, timeout=30)
        return "osd" in (proc.stdout or "")
    except Exception:
        return False


def _font():
    from PIL import ImageFont

    for name in FONT_CANDIDATES:
        if Path(name).exists():
            return ImageFont.truetype(name, 28)
    return None


def _text_image() -> bytes:
    """多行文字整页图（OSD 需要足量文字才给方向）。"""
    from PIL import Image, ImageDraw

    font = _font()
    if font is None:
        pytest.skip("无可用 TrueType 字体")
    img = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        "INVOICE NUMBER: 2026-0919",
        "DATE: 2002-01-15",
        "AMOUNT DUE: 1,234.56",
        "SUPPLIER: China Mobile Hong Kong",
        "PURCHASE ORDER: CMHK-2024-003",
        "TOTAL QUANTITY: 128 PIECES",
        "PAYMENT TERMS: NET 30 DAYS",
        "BANK ACCOUNT: 9558 8000 1234",
        "TAX IDENTIFICATION: 91440300MA5D",
        "DELIVERY ADDRESS: KOWLOON BAY",
    ] * 3
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 44
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not _tesseract_ready(), reason="环境无 tesseract/osd")
def test_osd_detects_sideways_text() -> None:
    from PIL import Image

    upright = _text_image()
    assert detect_orientation_osd(upright) == 0
    img = Image.open(BytesIO(upright))
    rotated = img.transpose(Image.ROTATE_90)  # 逆时针转 90 → 需顺时针 90 回正
    buf = BytesIO()
    rotated.save(buf, format="PNG")
    assert detect_orientation_osd(buf.getvalue()) == 90


@pytest.mark.skipif(not _tesseract_ready(), reason="环境无 tesseract/osd")
def test_osd_blank_image_returns_zero() -> None:
    from PIL import Image

    img = Image.new("RGB", (400, 600), "white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    assert detect_orientation_osd(buf.getvalue()) == 0


@pytest.mark.skipif(not _tesseract_ready(), reason="环境无 tesseract/osd")
def test_render_page_auto_rotate_straightens() -> None:
    """歪页 PDF 渲染：auto_rotate=True 出来的图应是正的。"""
    import pymupdf as fitz
    from PIL import Image

    sideways = Image.open(BytesIO(_text_image())).transpose(Image.ROTATE_90)
    buf = BytesIO()
    sideways.save(buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_image(page.rect, stream=buf.getvalue())
    try:
        straight = render_page(page, scale=1.5, image_format="png", auto_rotate=True)
        raw = render_page(page, scale=1.5, image_format="png", auto_rotate=False)
        assert detect_orientation_osd(raw) == 90
        assert detect_orientation_osd(straight) == 0
    finally:
        doc.close()


def test_ocrmypdf_cmd_rotate_flag() -> None:
    from command_shared.pdf_ocr import _build_cmd

    cmd = _build_cmd(Path("a.pdf"), Path("b.pdf"), languages="chi_sim+eng",
                     jobs=1, oversample=2, deskew=True, clean=False, force=False,
                     rotate=True)
    assert "--rotate-pages" in cmd
    cmd_off = _build_cmd(Path("a.pdf"), Path("b.pdf"), languages="chi_sim+eng",
                         jobs=1, oversample=2, deskew=True, clean=False, force=False,
                         rotate=False)
    assert "--rotate-pages" not in cmd_off
