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


def render_page(page, scale: float = 2.0, max_side: int = 2200, image_format: str = "jpeg") -> bytes:
    """单页渲染为图片字节；长边超 max_side 动态降 scale（大幅面图纸缩小，常规页不动）。"""
    if max_side and max_side > 0:
        longest = max(page.rect.width, page.rect.height) * scale
        if longest > max_side:
            scale *= max_side / longest
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pixmap.tobytes(image_format)


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
