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


def _is_ole2(path: Path) -> bool:
    """OLE2 复合文档魔数（旧版 .doc/.xls/.ppt 都是它）。"""
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except OSError:
        return False


def run(input: dict, ctx, emit) -> dict:
    from core.errors import ToolDomainError, ToolPauseError

    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")
    # 旧版 .doc（OLE2 容器，魔数 D0CF11E0）python-docx 无法解析 → 暂停子任务等人工另存为 .docx。
    # 用魔数而非后缀：误命名为 .docx 的二进制 .doc 同样拦下，避免后面报「文件损坏」这类无效错误。
    if path.suffix.lower() == ".doc" or _is_ole2(path):
        raise ToolPauseError(
            "旧版 .doc 格式（二进制 OLE2）无法直接翻译，请在 Word/WPS 中『另存为 .docx』后重新上传",
            hint="另存为 .docx 后：用新文件替换原路径再点本任务「继续」，或直接重新上传新文件",
        )

    # Word 临时锁文件（~$ 开头，Word 未正常关闭时残留）：不是文档，直接暂停留档等用户处理
    if path.name.startswith("~$"):
        raise ToolPauseError(
            "这是 Word 临时锁文件（~$ 开头），不是文档本体",
            hint="删除该文件后重新上传目录；或用『替换原件』传入真正的 .docx 再点「继续」",
        )

    from docx import Document

    from command_shared.docx_units import extract_units

    try:
        document = Document(str(path))
    except Exception as exc:  # noqa: BLE001 —— 损坏/非 docx（含 PackageNotFoundError/BadZipFile）
        raise ToolPauseError(
            f"无法打开该 .docx（文件已损坏或不是有效 Word 文档）：{type(exc).__name__}",
            hint="用 Word/WPS 另存为一份新的 .docx，再用『替换原件』换上来后点「继续」",
        ) from exc
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
