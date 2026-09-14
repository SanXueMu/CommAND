"""术语表解析（文本链与图片链共用）。

接受两种形态：
- 字符串：每行「原文 => 译文」，兼容 tab / -> / → / ＝ 分隔，`#` 开头为注释
- 列表：`[[原文, 译文], ...]` 或 `[{"src": ..., "tgt": ...}, ...]`
"""
from __future__ import annotations

_SEPARATORS = ("=>", "\t", "->", "→", "＝")


def parse_terms(raw) -> list[tuple[str, str]]:
    """→ [(原文, 译文), ...]（保序、去空）。"""
    if not raw:
        return []
    if isinstance(raw, str):
        pairs: list[tuple[str, str]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in _SEPARATORS:
                if sep in line:
                    src, _, tgt = line.partition(sep)
                    if src.strip() and tgt.strip():
                        pairs.append((src.strip(), tgt.strip()))
                    break
        return pairs

    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            src, tgt = str(item.get("src") or "").strip(), str(item.get("tgt") or "").strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            src, tgt = str(item[0]).strip(), str(item[1]).strip()
        else:
            continue
        if src and tgt:
            out.append((src, tgt))
    return out


def as_terminologies(raw, limit: int = 500) -> list[dict[str, str]]:
    """→ DashScope 图片翻译 `terminologies: [{src, tgt}]` 形态（带条数上限）。"""
    return [{"src": src, "tgt": tgt} for src, tgt in parse_terms(raw)[:limit]]
