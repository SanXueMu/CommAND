"""docx 译文回填：单元组 × 译文 → 原位覆盖单语 docx / 段落对照双语 docx（保留原版式）。

与 pdf.render.translated 同名对齐：
- `mode=overlay`   原位覆盖：正文段落/表格单元格替换为译文，保留样式、标题级别、图片、表格边框
- `mode=bilingual` 段落对照：原文段落后插入译文段（复用标题样式、深蓝字），表格在格内另起一段
默认 `bilingual`（双语对照）；源文件只读，产物写入 outputs/<handle>/。
"""
from __future__ import annotations

import os
from pathlib import Path

MODE_LABELS = {"overlay": "原位译文", "bilingual": "双语对照"}


def run(input: dict, ctx, emit) -> dict:
    from core.errors import ToolDomainError

    path = Path(input["file"])
    if not path.is_file():
        raise ToolDomainError(f"文件不存在: {path}")
    mode = (input.get("mode") or "bilingual").strip()
    if mode not in MODE_LABELS:
        raise ToolDomainError(f"未知渲染模式: {mode}（可选 overlay / bilingual）")
    units = input.get("units") or []
    if not units:
        raise ToolDomainError("units 为空：请先用 docx.extract.units 提取单元组")
    if not input.get("translations"):
        raise ToolDomainError("translations 为空：请先完成翻译")

    from docx import Document

    from command_shared.docx_render import build_document_from_units, render_document

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = input.get("output_name") or f"{path.stem}_{MODE_LABELS[mode]}.docx"
    out_path = out_dir / out_name

    # 源是 docx → 在原文件副本上回填（保留样式/图片/表格）；否则（pdf/txt 文档翻译链）
    # 按单元新建骨架——这两条流的产物就是「双语 docx」，没有可回填的原 docx。
    built = False
    element_map = None
    if path.suffix.lower() in (".docx", ".docm"):
        try:
            document = Document(str(path))
        except Exception:  # noqa: BLE001 —— 非 docx 包（伪装后缀/损坏）退化为新建
            document, element_map, built = *build_document_from_units(units), True
    else:
        document, element_map, built = *build_document_from_units(units), True
    stats = render_document(
        document,
        units=units,
        ranges=input.get("ranges"),
        index_map=input.get("index_map"),
        date_maps=input.get("date_maps"),
        translations=input.get("translations"),
        statuses=input.get("statuses"),
        col_classes=input.get("col_classes"),
        element_map=element_map,
        mode=mode,
        mark_review=bool(input.get("mark_review", True)),
    )
    document.save(str(out_path))

    emit({"phase": "rendered", "mode": mode, "path": str(out_path),
          "built_from_units": built, **stats})
    return {"path": str(out_path), "name": out_name, "mode": mode,
            "built_from_units": built, **stats}
