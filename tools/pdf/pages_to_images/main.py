"""PDF → 每页图片（图片翻译链第 1 步）。

- 复用 `command_shared.ocr_render.render_page`：倍率 + 长边上限，大幅面自动降采样
- 顺带上报 `page_count` / `has_text_layer`（工作台据此自动判断扫描件、选图片流）
- 页图写入 `outputs/<handle>/tmp_pages/`（中间产物，由末步 `pdf.from.images` 清理）
- 源 PDF 只读
"""
from __future__ import annotations

import os
from pathlib import Path


def _error(message: str):
    from core.errors import ToolDomainError

    return ToolDomainError(message)


def _effective_scale(width: float, height: float, scale: float, max_side: int) -> float:
    """与 render_page 内部同一套长边收缩算法（用于如实回报渲染像素尺寸）。"""
    if max_side and max_side > 0:
        longest = max(width, height) * scale
        if longest > max_side:
            return scale * max_side / longest
    return scale


def run(input: dict, ctx, emit) -> dict:
    import fitz  # pymupdf

    from command_shared.ocr_render import is_text_pdf, render_page

    path = Path(input["file"])
    if not path.is_file():
        raise _error(f"文件不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise _error(f"仅支持 PDF（OCR 工作台的图片请直接用 image.mt.translate）：{path.name}")

    scale = float(input.get("scale") or 2.0)
    max_side = int(input.get("max_side") or 2200)
    fmt = str(input.get("format") or "jpeg").lower()
    if fmt not in ("jpeg", "png"):
        raise _error(f"不支持的图片格式: {fmt}")
    ext = ".png" if fmt == "png" else ".jpg"

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc") / str(input.get("dir_name") or "tmp_pages")
    out_dir.mkdir(parents=True, exist_ok=True)

    min_chars = int(input.get("min_chars_per_page") or 20)
    has_text = is_text_pdf(path, min_chars_per_page=min_chars)
    if has_text:
        emit({"phase": "notice", "message": "该 PDF 含文字层，图片翻译会整页当图处理（文字版建议用版式流）"})

    wanted = input.get("pages")
    images: list[dict] = []
    effective = scale
    with fitz.open(path) as doc:
        total = doc.page_count
        wanted = [int(p) for p in (wanted or range(1, total + 1))]
        targets = [p for p in wanted if 1 <= p <= total]
        for n in targets:
            page = doc[n - 1]
            effective = _effective_scale(page.rect.width, page.rect.height, scale, max_side)
            dest = out_dir / f"page_{n:04d}{ext}"
            dest.write_bytes(render_page(page, scale=scale, max_side=max_side, image_format=fmt))
            images.append({
                "page": n, "path": str(dest), "name": dest.name, "size": dest.stat().st_size,
                "width": round(page.rect.width * effective), "height": round(page.rect.height * effective),
            })
            if len(images) % 10 == 0:
                emit({"phase": "rendering", "done": len(images), "total": len(targets)})

    emit({"phase": "rendered", "pages": len(images), "has_text_layer": has_text, "dir": str(out_dir)})
    return {
        "file": str(path),
        "page_count": total,
        "rendered": len(images),
        "has_text_layer": has_text,
        "format": fmt,
        "scale": scale,
        "effective_scale": round(effective, 3),
        "dir": str(out_dir),
        "paths": [i["path"] for i in images],
        "images": images,
    }
