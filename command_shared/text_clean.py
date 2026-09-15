"""文本清洗：去除 XML 不兼容字符（控制字符 / NULL / 孤立代理对）。

背景：python-docx（lxml）写入含控制字符的文本会抛
``ValueError: All strings must be XML compatible: Unicode or ASCII, no NULL bytes or control characters``。
扫描件 OCR 输出或损坏的字体 ToUnicode 映射都可能带这类字符，故在提取入口统一清洗。
"""
from __future__ import annotations

import re

# XML 1.0 非法字符：C0 控制字符（保留 \t=\x09 \n=\x0a \r=\x0d）、DEL、C1 控制字符、孤立代理对
_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]")


def xml_safe_text(text: str | None) -> str:
    """去除 XML 不兼容字符；保留 \\t \\n \\r 与全部常规 Unicode（含 U+FFFD）。最小干预，不改语义。"""
    if not text:
        return text or ""
    return _ILLEGAL_RE.sub("", text)
