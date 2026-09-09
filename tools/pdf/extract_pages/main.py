"""文本型 PDF → 每页 text 单元 + 表格 table 单元（translee extract_pdf 移植）。

- 页眉/页脚过滤：全文档预扫，页首/页尾重复出现（≥ 页数 1/3，至少 3 次）的行整行丢弃
- 页码行：模式匹配丢弃（Page N / 第N页 / N / M）
- 表格：pymupdf find_tables → table 单元（复用 xlsx 列分类管线）
- 扫描页（无文本且无表格）标记 no_text
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

_PAGE_NO_PATTERNS = [
    re.compile(r"^page\s*\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^第\s*\d+\s*页(\s*[,，]?\s*共\s*\d+\s*页)?$"),
    re.compile(r"^\d+\s*/\s*\d+$"),
    re.compile(r"^[-—–]\s*\d+\s*[-—–]$"),
]


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1048576):
            h.update(chunk)
    return h.hexdigest()


def _is_page_number_line(line: str) -> bool:
    text = line.strip()
    return any(p.match(text) for p in _PAGE_NO_PATTERNS)


def _page_tables(page) -> list[list[list[str]]]:
    try:
        found = page.find_tables()
        tables = getattr(found, "tables", None) or []
    except Exception:
        return []
    result = []
    for tab in tables:
        rows = [[(c or "").strip() for c in row] for row in tab.extract()]
        rows = [r for r in rows if any(x for x in r)]
        if rows:
            result.append(rows)
    return result


def run(input: dict, ctx, emit) -> dict:
    path = Path(input["file"])
    if not path.is_file():
        from core.errors import ToolDomainError

        raise ToolDomainError(f"文件不存在: {path}")

    import pymupdf

    fhash = _file_hash(path)
    units = []
    with pymupdf.open(path) as doc:
        pages_lines = []
        for page in doc:
            pages_lines.append([l.strip() for l in page.get_text().splitlines()])
        npages = len(pages_lines)
        threshold = max(3, (npages + 2) // 3)
        counter: Counter = Counter()
        for lines in pages_lines:
            for line in lines[:2] + lines[-2:]:
                if line:
                    counter[line] += 1
        repeated = {l for l, c in counter.items() if c >= threshold and len(l) >= 2}

        for i, page in enumerate(doc, start=1):
            lines = pages_lines[i - 1]
            for k, rows in enumerate(_page_tables(page), start=1):
                units.append({
                    "unit_id": f"{i}T{k}", "unit_type": "table",
                    "rows": rows, "meta": {"page": i},
                })
            kept = [l for l in lines if l and l not in repeated and not _is_page_number_line(l)]
            text = "\n".join(kept).strip()
            units.append({
                "unit_id": str(i), "unit_type": "text", "text": text,
                "meta": {"page": i, **({"no_text": True} if not text else {})},
            })
            if i % 10 == 0:
                emit({"phase": "extracting", "page": i, "total": npages})

    emit({"phase": "extracted", "pages": npages, "units": len(units)})
    return {"file": str(path), "file_hash": fhash, "kind": "pdf", "units": units}
