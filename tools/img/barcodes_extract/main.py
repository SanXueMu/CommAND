"""条码/二维码提取（pyzbar）：PDF 逐页渲染解码 或 图片直接解码。

零 LLM 成本（纯本地 zbar 解码）；pyzbar 需系统 zbar 库（容器 apt libzbar0），
缺失时抛带指引的域错误。资产盘点场景：设备标签扫码 ↔ 台账比对。
"""
from __future__ import annotations

import json
from pathlib import Path

from command_shared.ocr_render import is_image_file, open_document, render_page
from core.errors import ToolDomainError

try:
    from pyzbar.pyzbar import decode as _zbar_decode
except ImportError as exc:  # 系统 zbar 库缺失
    _zbar_decode = None
    _ZBAR_HINT = (
        "pyzbar 不可用：需安装系统 zbar 库（macOS: brew install zbar / "
        "Debian 系: apt install libzbar0）后重试"
    )
    _ZBAR_exc = exc


def _decode(image_bytes: bytes, page_number: int, scale: float, max_side: int) -> list[dict]:
    import io

    from PIL import Image
    image = Image.open(io.BytesIO(image_bytes))
    found = []
    for item in _zbar_decode(image):
        data = item.data.decode("utf-8", errors="replace")
        rect = item.rect
        found.append({
            "页码": page_number,
            "value": data,
            "type": item.type,
            "x": rect.left, "y": rect.top,
            "w": rect.width, "h": rect.height,
        })
    return found


def run(input: dict, ctx, emit) -> dict:
    if _zbar_decode is None:
        raise ToolDomainError(_ZBAR_HINT) from _ZBAR_exc
    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")

    scale = float(input.get("render_scale", 2.0))
    max_side = int(input.get("image_max_side", 0) or 0)  # 条码识别不降采样
    barcodes: list[dict] = []

    if is_image_file(path):
        barcodes = _decode(path.read_bytes(), 1, scale, max_side)
        pages = 1
        emit({"type": "progress", "phase": "decode", "message": "图片解码完成"})
    else:
        doc = open_document(path)
        try:
            pages = doc.page_count
            for index in range(pages):
                image_bytes = render_page(doc.load_page(index), scale, max_side, "png")
                barcodes.extend(_decode(image_bytes, index + 1, scale, max_side))
                if (index + 1) % 5 == 0 or index + 1 == pages:
                    emit({"type": "progress", "phase": "decode",
                          "message": f"已解码 {index + 1}/{pages} 页"})
        finally:
            doc.close()

    # 去重（同值同类型跨页保留多页出现）
    seen = set()
    unique = []
    for item in barcodes:
        key = (item["value"], item["type"], item["页码"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return {"file": str(path), "barcodes": unique, "count": len(unique),
            "values": sorted({item["value"] for item in unique}),
            "pages": pages}
