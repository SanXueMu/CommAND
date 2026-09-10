"""PDF 逐页渲染为 base64 图片（filekit render 移植）——独立通用工具。

仅用于独立调用/调试（把 PDF 页交给任意视觉模型或人工查看）。
管线场景不要用它：base64 大 payload 不上管线总线，img.vl.extract 内部已渲染。
长边超 max_side 动态降 scale（大幅面缩小，常规页不动）。
"""
from __future__ import annotations

import base64
from pathlib import Path

from command_shared.ocr_render import is_image_file, open_document, render_page
from core.errors import ToolDomainError

MAX_OUTPUT_PAGES = 50


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")

    scale = float(input.get("render_scale", 2.0))
    max_side = int(input.get("image_max_side", 2200))
    image_format = input.get("image_format") or "jpeg"

    pages = []
    if is_image_file(path):
        pages.append({"page": 1, "image_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
        total = 1
    else:
        doc = open_document(path)
        try:
            total = doc.page_count
            if total > MAX_OUTPUT_PAGES:
                raise ToolDomainError(f"页数 {total} 超输出上限 {MAX_OUTPUT_PAGES}（大 payload 工具，勿用于整本大文档）")
            for index in range(total):
                image_bytes = render_page(doc.load_page(index), scale, max_side, image_format)
                pages.append({"page": index + 1,
                              "image_base64": base64.b64encode(image_bytes).decode("ascii")})
                if (index + 1) % 10 == 0:
                    emit({"type": "progress", "phase": "render",
                          "message": f"已渲染 {index + 1}/{total} 页"})
        finally:
            doc.close()

    return {"file": str(path), "pages": pages, "page_count": total}
