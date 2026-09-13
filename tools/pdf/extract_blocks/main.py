"""版式感知 PDF 提取：文字/表格块 + bbox（供原位叠加 / 双语对照翻译）。

- 块级粒度：文字块（段落）+ 表格块（含逐格 bbox），按阅读顺序（上→下、左→右）排序
- 自动 OCR：`auto_ocr=true` 时检测扫描页并先补隐形文字层（OCRmyPDF）再提取
- 不过滤页眉页脚：叠加需保留原页全部内容
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {path}")

    import pymupdf

    from command_shared import pdf_ocr
    from command_shared.pdf_blocks import extract_blocks

    ocr = {"ocr_applied": False, "layered_file": None, "layered_name": None, "pages_ocr": 0}
    source = path
    if bool(input.get("auto_ocr")):
        if pdf_ocr.needs_ocr(path, min_chars_per_page=int(input.get("min_chars_per_page") or 20)):
            emit({"phase": "ocr", "message": "检测到扫描页，正在补文字层…"})
            data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
            out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_name = f"{path.stem}_可搜索.pdf"
            res = pdf_ocr.add_ocr_layer(
                path, out_dir / out_name,
                languages=(input.get("ocr_languages") or pdf_ocr.DEFAULT_LANGUAGES).strip(),
                jobs=int(input.get("ocr_jobs") or pdf_ocr.DEFAULT_JOBS),
                max_pages=int(input.get("ocr_max_pages") or pdf_ocr.DEFAULT_MAX_PAGES),
                timeout_s=int(input.get("ocr_timeout_s") or pdf_ocr.DEFAULT_TIMEOUT_S),
                progress=lambda e: emit(e),
            )
            if res["applied"]:
                source = Path(res["path"])
                ocr = {"ocr_applied": True, "layered_file": res["path"],
                        "layered_name": out_name, "pages_ocr": res["pages_ocr"]}

    include_tables = bool(input.get("include_tables", True))
    with pymupdf.open(source) as doc:
        npages = len(doc)
        blocks = extract_blocks(doc, include_tables=include_tables)
        for b in blocks:
            if b["page"] % 10 == 0:
                emit({"phase": "extracting", "page": b["page"], "total": npages})

    emit({"phase": "extracted", "pages": npages, "blocks": len(blocks)})
    return {"file": str(path), "file_hash": _file_hash(path), "kind": "pdf_blocks",
            "pages": npages, "blocks": blocks, "render_file": str(source), **ocr}
