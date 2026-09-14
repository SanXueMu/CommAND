"""版式翻译渲染：overlay（原位覆盖单语）/ bilingual（左右分栏双语对照）。

输入版式块（pdf.extract.blocks）+ 去重/翻译链产物（index_map/date_maps/translations/statuses），
按 flatten 顺序重建终译文本后渲染；产出质检统计（drawn/overflow）。
"""
from __future__ import annotations

import os
from pathlib import Path

MODES = ("overlay", "bilingual")


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {path}")

    blocks = input.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        from core.errors import ToolDomainError

        raise ToolDomainError("blocks 为空：请先用 pdf.extract.blocks 提取版式块")
    translations = input.get("translations")
    if not isinstance(translations, list) or not translations:
        from core.errors import ToolDomainError

        raise ToolDomainError("translations 为空：缺少译文")

    # 默认双语对照（用户口径 2026-09-14）；原位覆盖需显式传 mode=overlay
    mode = (input.get("mode") or "bilingual").strip()
    if mode not in MODES:
        from core.errors import ToolDomainError

        raise ToolDomainError(f"mode 仅支持 {MODES}，收到 {mode!r}")

    from command_shared import pdf_layout

    base_size = float(input.get("font_size") or 11)
    min_size = float(input.get("min_font_size") or 5)
    col_width = float(input.get("col_width") or 300)

    items = pdf_layout.reconstruct(
        blocks, input.get("index_map"), input.get("date_maps"),
        translations, input.get("statuses"))

    data_dir = Path(os.environ.get("COMMAND_DATA_DIR", "data"))
    out_dir = data_dir / "outputs" / getattr(ctx, "handle", "adhoc")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "原位译文" if mode == "overlay" else "双语对照"
    out_name = input.get("output_name") or f"{path.stem}_{suffix}.pdf"
    out_path = out_dir / out_name

    font_path = pdf_layout.cjk_font_path()
    emit({"phase": "render", "mode": mode, "segments": len(items),
          "font": font_path.name if font_path else "china-ss"})

    filler = lambda e: emit(e)  # noqa: E731
    if mode == "overlay":
        stats = pdf_layout.render_overlay(path, out_path, items, font_path, base_size, min_size, filler)
    else:
        stats = pdf_layout.render_bilingual(path, out_path, items, font_path, base_size, min_size,
                                            filler, col_width=col_width)

    emit({"phase": "rendered", "mode": mode, "overflow": stats["overflow"]})
    return {"path": str(out_path), "name": out_name, "mode": mode,
            "pages": stats["pages"], "segments": len(items),
            "drawn": stats["drawn"], "overflow": stats["overflow"],
            "font": font_path.name if font_path else "china-ss(内置)"}
