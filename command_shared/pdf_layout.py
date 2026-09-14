"""版式翻译渲染：原位覆盖（overlay）与左右分栏双语对照（bilingual）。

- overlay：先 `apply_redactions`（擦原文字形/像素、保留线条），再按块框写中文（自动缩放）
- bilingual：不改动原页，新页左侧贴原页、右侧按块序排中文
- 中文字体：内嵌 Noto Sans SC（assets/fonts），缺失时回退 PyMuPDF 内置 china-ss
"""
from __future__ import annotations

import html
import os
from pathlib import Path

FONT_NAME = "notosc"
FALLBACK_FONT = "china-ss"


def cjk_font_path() -> Path | None:
    env = os.environ.get("COMMAND_CJK_FONT")
    if env and Path(env).is_file():
        return Path(env)
    cand = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
    return cand if cand.is_file() else None


def reconstruct(blocks: list[dict], index_map, date_maps, translations, statuses) -> list[dict]:
    """按 flatten_blocks 顺序重建每段的终译文本（含日期回插）。"""
    from command_shared.pdf_blocks import flatten_blocks

    items = []
    for it in flatten_blocks(blocks):
        g = it["index"]
        u = index_map[g] if index_map and g < len(index_map) else g
        text = translations[u] if u < len(translations) else it["text"]
        dates = date_maps[g] if date_maps and g < len(date_maps) else None
        for placeholder, value in (dates or {}).items():
            text = text.replace(placeholder, value)
        items.append({**it, "translated": text,
                      "status": statuses[u] if statuses and u < len(statuses) else "ok"})
    return items


def _register_font(page, font_path: Path | None) -> str:
    if font_path is not None:
        page.insert_font(fontname=FONT_NAME, fontfile=str(font_path))
        return FONT_NAME
    return FALLBACK_FONT


def _fit_height(spare) -> float:
    if isinstance(spare, (tuple, list)):
        return float(spare[0])
    return float(spare)


def _draw(page, rect, text: str, font: str, size: float, min_size: float, color: str = "#111111") -> float:
    css = f"* {{ font-family: {font}; font-size: {size}px; line-height: 1.15; color: {color}; }}"
    body = html.escape(text).replace("\n", "<br/>")
    scale_low = max(0.2, min(1.0, float(min_size) / float(size)))
    spare = page.insert_htmlbox(rect, f"<div>{body}</div>", css=css, scale_low=scale_low)
    return _fit_height(spare)


def render_overlay(src, out, items, font_path, base_size, min_size, emit) -> dict:
    import pymupdf

    doc = pymupdf.open(src)
    overflow = drawn = 0
    for page in doc:
        pno = page.number + 1
        ptxt = [it for it in items if it["page"] == pno]
        if not ptxt:
            continue
        font = _register_font(page, font_path)
        for it in ptxt:
            page.add_redact_annot(pymupdf.Rect(it["bbox"]))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        for it in ptxt:
            rect = pymupdf.Rect(it["bbox"])
            if rect.height < 6 or rect.width < 6:
                continue
            spare = _draw(page, rect, it["translated"], font, base_size, min_size,
                          color="#9b1c1c" if it["status"] == "review" else "#111111")
            drawn += 1
            if spare < 0:
                overflow += 1
        emit({"phase": "overlay", "page": pno})
    if font_path is not None:
        doc.subset_fonts()
    doc.save(out, garbage=4, deflate=True)
    pages = doc.page_count
    doc.close()
    return {"pages": pages, "drawn": drawn, "overflow": overflow}


def render_bilingual(src, out, items, font_path, base_size, min_size, emit,
                     col_width: float = 300.0, gap: float = 20.0) -> dict:
    import pymupdf

    src_doc = pymupdf.open(src)
    out_doc = pymupdf.open()
    overflow = drawn = 0
    for i in range(len(src_doc)):
        s = src_doc[i]
        w, h = s.rect.width, s.rect.height
        new = out_doc.new_page(width=w + gap + col_width, height=h)
        new.show_pdf_page(pymupdf.Rect(0, 0, w, h), src_doc, i)
        font = _register_font(new, font_path)
        tx0 = w + gap
        y = 36.0
        new.insert_text((tx0, y - 12), f"译文 · P{i + 1}", fontname=font, fontsize=9,
                        color=(0.45, 0.45, 0.45))
        for it in [x for x in items if x["page"] == i + 1]:
            avail = h - 30 - y
            if avail < 12:
                break
            rect = pymupdf.Rect(tx0, y, tx0 + col_width - 16, y + avail)
            spare = _draw(new, rect, it["translated"], font, base_size, min_size,
                          color="#9b1c1c" if it["status"] == "review" else "#111111")
            drawn += 1
            used = avail - spare
            if spare < 0:
                overflow += 1
                used = avail
            y += used + 8
        emit({"phase": "bilingual", "page": i + 1})
    if font_path is not None:
        out_doc.subset_fonts()
    out_doc.save(out, garbage=4, deflate=True)
    pages = out_doc.page_count
    out_doc.close()
    src_doc.close()
    return {"pages": pages, "drawn": drawn, "overflow": overflow}
