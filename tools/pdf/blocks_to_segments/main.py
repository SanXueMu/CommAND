"""PDF 版式块 → 翻译片段：每文字块/每表格单元格一段，附回填坐标（refs）。"""
from __future__ import annotations


def run(input: dict, ctx, emit) -> dict:  # noqa: ARG001
    blocks = input.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        from core.errors import ToolDomainError

        raise ToolDomainError("blocks 为空：请先用 pdf.extract.blocks 提取版式块")

    from command_shared.pdf_blocks import flatten_blocks

    items = flatten_blocks(blocks)
    segments = [it["text"] for it in items]
    if not segments:
        from core.errors import ToolDomainError

        raise ToolDomainError("未提取到可翻译文本片段")

    refs = []
    for it in items:
        ref = {"index": it["index"], "block_id": it["block_id"], "page": it["page"],
               "kind": it["kind"], "bbox": it["bbox"]}
        if it["kind"] == "cell":
            ref["row"] = it["row"]
            ref["col"] = it["col"]
        refs.append(ref)

    emit({"phase": "flattened", "segments": len(segments)})
    return {"segments": segments, "refs": refs}
