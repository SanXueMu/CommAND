"""docx 单元提取：段落/表格（正文流顺序）→ 通用单元组，接既有 classify→去重→翻译→质检→回填链。

- 与 pdf.extract.blocks 的差别：docx 无版面坐标，粒度为「段落 / 表格」，回填按 body 序号定位
- 跳过空段、纯数字段、域代码/目录段；页眉页脚/文本框/批注/脚注不在正文流（已知上限）
- 旧版 .doc 不支持（python-docx 无法解析），提示另存为 .docx
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def run(input: dict, ctx, emit) -> dict:
    from core.errors import ToolDomainError

    path = Path(input["file"])
    if path.suffix.lower() == ".doc":
        raise ToolDomainError("不支持旧版 .doc：请在 Word 中另存为 .docx 后重试")
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")

    from docx import Document

    from command_shared.docx_units import extract_units

    document = Document(str(path))
    result = extract_units(
        document,
        include_tables=bool(input.get("include_tables", True)),
        skip_numbers=bool(input.get("skip_numbers", True)),
    )
    units, stats = result["units"], result["stats"]
    if not units:
        raise ToolDomainError("未提取到可翻译内容（文档正文为空，或全为数字/域代码）")

    emit({"phase": "extracted", "units": len(units), "paragraphs": stats["paragraphs"],
          "tables": stats["tables"], "chars": stats["text_chars"]})
    return {"file": str(path), "file_hash": _file_hash(path), "kind": "docx_units",
            "units": units, "stats": stats}
