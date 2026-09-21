"""渲染与文件纯工具（CommOCR filekit + turn_pages 移植，零业务状态）。

来源：commocr/server/app/utils/filekit.py + scripts/turn_pages.py。
config 参数全部显式化（无全局 settings）。
"""
from __future__ import annotations

import base64
import hashlib
from collections import Counter
from pathlib import Path

import pymupdf as fitz
from PIL import Image

SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

_ROT = {(0.0, 1.0): 270, (0.0, -1.0): 90}


def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def calculate_file_hash(file_path, chunk_size: int = 1048576) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_page(page, scale: float = 2.0, max_side: int = 2200, image_format: str = "jpeg",
                auto_rotate: bool = False) -> bytes:
    """单页渲染为图片字节；长边超 max_side 动态降 scale（大幅面图纸缩小，常规页不动）。

    auto_rotate=True 时用 tesseract OSD 做内容方向检测，歪页（90/180/270）回正——
    扫描件无文字层，fitz 的 set_rotation 元数据不可信，只能按内容判。
    """
    if max_side and max_side > 0:
        longest = max(page.rect.width, page.rect.height) * scale
        if longest > max_side:
            scale *= max_side / longest
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    data = pixmap.tobytes(image_format)
    if auto_rotate:
        deg = detect_orientation_osd(data)
        if deg in _CW_TRANSPOSE:
            from io import BytesIO

            from PIL import Image

            img = Image.open(BytesIO(data))
            img = img.transpose(_CW_TRANSPOSE[deg])
            buf = BytesIO()
            fmt = "PNG" if image_format == "png" else "JPEG"
            save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
            img.save(buf, format=fmt, **save_kwargs)
            data = buf.getvalue()
    return data


# 顺时针旋转角度 → PIL transpose。PIL 的 ROTATE_* 是逆时针，故 CW90=ROTATE_270、CW270=ROTATE_90。
# ⚠ 别用数字字面量：Pillow 的 TRANSPOSE=5/TRANSVERSE=6 是镜像翻折不是旋转——
#   此前 90 分支误写 6 号导致歪页被镜像（像从纸背面看字），模型全页幻觉（2026-09-21 定案）。
_CW_TRANSPOSE = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}


def detect_orientation_osd(image_bytes: bytes, min_confidence: float = 0.0,
                           timeout_s: int = 60) -> int:
    """tesseract OSD（内容方向检测）：返回把图转正所需的顺时针角度（0/90/180/270）。

    无 tesseract / 无 osd 数据 / 置信度不足 → 0（宁可不误伤也不乱转）。
    min_confidence 默认 0（与 ocrmypdf --rotate-pages 的默认口径一致，信任 OSD）。
    """
    import os
    import re
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            png_path = tmp.name
        try:
            proc = subprocess.run(
                ["tesseract", png_path, "stdout", "--psm", "0"],
                capture_output=True, text=True, timeout=timeout_s, check=False)
        finally:
            os.unlink(png_path)
    except Exception:
        return 0
    text = proc.stdout or ""
    rot = re.search(r"^\s*Rotate:\s*(\d+)", text, re.M)
    if not rot:
        return 0
    conf = re.search(r"Orientation confidence:\s*([\d.]+)", text)
    if conf and float(conf.group(1)) < min_confidence:
        return 0
    return int(rot.group(1)) % 360


def is_text_pdf(file_path, min_chars_per_page: int = 20) -> bool:
    """全部页均有足量可提取文本 → 文本型 PDF（任一页无文本按扫描型处理）。"""
    if Path(file_path).suffix.lower() != ".pdf":
        return False
    try:
        with fitz.open(file_path) as document:
            return all(
                len(page.get_text().strip()) >= min_chars_per_page
                for page in document
            )
    except Exception:
        return False


def images_to_pdf(paths, dest_path) -> int:
    """图片序列 → 单 PDF（每页按图片像素尺寸建页，保持原页比例）；返回页数。

    用于图片翻译链末步：译文页图按页序合成译文 PDF。
    """
    items = [Path(p) for p in paths]
    if not items:
        raise ValueError("图片列表为空")
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        for path in items:
            img = fitz.Pixmap(path)
            if img.alpha:
                img = fitz.Pixmap(img, 0)
            page = doc.new_page(width=img.width, height=img.height)
            page.insert_image(page.rect, pixmap=img)
        doc.save(dest)
        pages = doc.page_count
    finally:
        doc.close()
    return pages


def is_image_file(file_path) -> bool:
    return Path(file_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def open_document(file_path):
    """打开 PDF 或单页图片文档（图片包装为单页 fitz 文档）。"""
    path = Path(file_path)
    if is_image_file(path):
        doc = fitz.open()
        img = fitz.Pixmap(path)
        if img.alpha:
            img = fitz.Pixmap(img, 0)
        page = doc.new_page(width=img.width, height=img.height)
        page.insert_image(page.rect, pixmap=img)
        return doc
    return fitz.open(path)


def dominant_dir(page):
    """按字符数加权的主导书写方向 (dx, dy)；无文字页返回 None。"""
    votes: Counter = Counter()
    for blk in page.get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            txt = "".join(s["text"] for s in line["spans"]).strip()
            if txt:
                votes[tuple(round(v, 1) for v in line["dir"])] += len(txt)
    return votes.most_common(1)[0][0] if votes else None


def straighten_pdf(src, dst_path) -> int:
    """逐页方向转正（(0,1)→270°，(0,-1)→90°；180° 与无文字页不动），返回转正页数。"""
    doc = fitz.open(src)
    try:
        turned = 0
        for page in doc:
            d = dominant_dir(page)
            if d in _ROT:
                page.set_rotation(_ROT[d])
                turned += 1
        doc.save(dst_path)
        return turned
    finally:
        doc.close()
