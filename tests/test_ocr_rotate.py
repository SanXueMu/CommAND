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


def test_cw_transpose_is_pure_rotation() -> None:
    """AR-1 守卫：_CW_TRANSPOSE 每个分支必须是真旋转，绝不能映射到镜像翻折。

    背景：Pillow 的 5/6 号是 TRANSPOSE/TRANSVERSE（镜像），不是旋转。此前 90 分支
    误写 6 号，歪页被镜像（像从纸背面看字），模型只能全页幻觉——用非对称字形守卫。
    无 tesseract 依赖，任何环境都可跑。
    """
    from PIL import Image

    from command_shared.ocr_render import _CW_TRANSPOSE

    W, H = 40, 24
    img = Image.new("L", (W, H), 0)
    for x in range(4, 30):          # 顶横杠
        img.putpixel((x, 4), 255)
    for y in range(4, 20):          # 左竖杠 → 构成非对称「┐」形
        img.putpixel((4, y), 255)
    for x in range(4, 18):          # 中横杠 → 「F」形
        img.putpixel((x, 11), 255)

    # 真旋转的唯一性：CW90 必须等于 ROTATE_270，且绝不等于任何镜像翻折
    assert _CW_TRANSPOSE[90] == Image.ROTATE_270
    assert _CW_TRANSPOSE[180] == Image.ROTATE_180
    assert _CW_TRANSPOSE[270] == Image.ROTATE_90
    for deg in (90, 180, 270):
        rotated = img.transpose(_CW_TRANSPOSE[deg])
        mirrored = {img.transpose(m).tobytes() for m in
                    (Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM,
                     Image.TRANSPOSE, Image.TRANSVERSE)}
        assert rotated.tobytes() not in mirrored, f"{deg}° 分支落进了镜像翻折"


@pytest.mark.skipif(not _tesseract_ready(), reason="环境无 tesseract/osd")
def test_render_page_rotated_output_is_readable() -> None:
    """AR-1 端到端：回正后的图必须能被 OCR 读出原文——镜像图行也水平、OSD 照样报 0，
    只断言 OSD 拦不住镜像 bug（本批漏网原因），必须以可读性为准绳。"""
    import subprocess
    import tempfile

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
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(straight)
            path = tmp.name
        proc = subprocess.run(["tesseract", path, "stdout", "-l", "eng", "--psm", "3"],
                              capture_output=True, text=True, timeout=60, check=False)
        text = (proc.stdout or "").replace(" ", "").upper()
        assert "INVOICE" in text and "2026-0919" in text.replace("O", "0"), \
            f"回正产物 OCR 读不出原文（疑似镜像/方向错）：{text[:120]!r}"
    finally:
        doc.close()
