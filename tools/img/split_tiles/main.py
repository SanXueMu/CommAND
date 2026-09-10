"""大图切块（A0/A1 图纸场景）：图或 PDF 页 → 重叠瓦片 + 全局坐标。

大幅面整图送 VL 会因长边降采样丢失小字；切块后逐块识别再按坐标回拼。
输出 tiles 含 (x, y, w, h) 全局像素坐标与 image_base64——独立工具，勿进管线
（base64 大 payload 不上总线，管线场景用 img.vl.extract 内部渲染）。
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

from command_shared.ocr_render import is_image_file, open_document, render_page
from core.errors import ToolDomainError


def _tile_page(image, page_number: int, tile_size: int, overlap: int, max_tiles: int):
    width, height = image.size
    step = max(1, tile_size - overlap)
    tiles = []
    ys = list(range(0, max(1, height - overlap), step)) or [0]
    xs = list(range(0, max(1, width - overlap), step)) or [0]
    for y in ys:
        for x in xs:
            box = (x, y, min(x + tile_size, width), min(y + tile_size, height))
            if box[2] - box[0] < 8 or box[3] - box[1] < 8:
                continue
            buffer = io.BytesIO()
            image.crop(box).save(buffer, format="PNG")
            tiles.append({
                "page": page_number,
                "index": len(tiles),
                "x": box[0], "y": box[1],
                "w": box[2] - box[0], "h": box[3] - box[1],
                "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            })
            if len(tiles) >= max_tiles:
                raise ToolDomainError(
                    f"切块数超上限 {max_tiles}：请调大 tile_size 或先拆分文档")
    return tiles


def run(input: dict, ctx, emit) -> dict:
    from PIL import Image

    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")
    tile_size = int(input.get("tile_size", 1600))
    overlap = int(input.get("overlap", 120))
    max_tiles = int(input.get("max_tiles", 200))
    scale = float(input.get("render_scale", 2.0))

    tiles: list[dict] = []
    if is_image_file(path):
        image = Image.open(path).convert("RGB")
        tiles = _tile_page(image, 1, tile_size, overlap, max_tiles)
        pages = 1
    else:
        doc = open_document(path)
        try:
            pages = doc.page_count
            for index in range(pages):
                image_bytes = render_page(doc.load_page(index), scale, 0, "png")
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                tiles.extend(_tile_page(image, index + 1, tile_size, overlap, max_tiles))
                emit({"type": "progress", "phase": "tile",
                      "message": f"已切块 {index + 1}/{pages} 页，累计 {len(tiles)} 块"})
        finally:
            doc.close()

    return {"file": str(path), "tiles": tiles, "tile_count": len(tiles),
            "pages": pages, "tile_size": tile_size, "overlap": overlap}
