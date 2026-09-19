"""扫描版 PDF → 可搜索 PDF：补一层隐形文字层（OCRmyPDF + Tesseract）。

- 自动检测：全部含文字层则原样返回（applied=False），不重复识别
- 混合文档：`--skip-text` 只对无文字层的页 OCR，已有页不动
- 输出落在 `data/outputs/<handle>/<原名>_可搜索.pdf`
"""
from __future__ import annotations

import os
from pathlib import Path

from command_shared.pdf_ocr import (
    DEFAULT_JOBS,
    DEFAULT_LANGUAGES,
    DEFAULT_MAX_PAGES,
    DEFAULT_OVERSAMPLE,
    DEFAULT_TIMEOUT_S,
    add_ocr_layer,
    calculate_file_hash,
)


def run(input: dict, ctx, emit) -> dict:
    src = Path(input["file"])
    if not src.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {src}")

    languages = (input.get("languages") or DEFAULT_LANGUAGES).strip()
    jobs = int(input.get("jobs") or DEFAULT_JOBS)
    max_pages = int(input.get("max_pages") or DEFAULT_MAX_PAGES)
    timeout_s = int(input.get("timeout_s") or DEFAULT_TIMEOUT_S)
    oversample = int(input.get("oversample") or DEFAULT_OVERSAMPLE)
    deskew = bool(input.get("deskew", True))
    force = bool(input.get("force", False))
    _rt = input.get("rotate")
    rotate = True if _rt is None else bool(_rt)

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / ctx.handle
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = input.get("output_name") or f"{src.stem}_可搜索.pdf"
    out_path = out_dir / out_name

    result = add_ocr_layer(
        src, out_path,
        languages=languages, jobs=jobs, oversample=oversample,
        deskew=deskew, max_pages=max_pages, timeout_s=timeout_s, force=force,
        rotate=rotate,
        progress=lambda e: emit(e),
    )

    emit({"phase": "layered", "applied": result["applied"],
          "pages": result["pages"], "pages_ocr": result["pages_ocr"]})
    return {
        "file": result["path"],
        "source": str(src),
        "file_hash": calculate_file_hash(src),
        "pages": result["pages"],
        "pages_ocr": result["pages_ocr"],
        "applied": result["applied"],
        "languages": result["languages"],
    }
