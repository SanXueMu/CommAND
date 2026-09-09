"""日期归一：数字型日期 → [[DATE_n]] 占位符（纯函数，零 IO）。

移植自 translee classify.py。仅日期不同的条目归一后可合并去重，翻译完由调用方回插原日期。
"""
from __future__ import annotations

import re

DATE_RES: tuple = (
    re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"),  # 2023-11-16 / 2023/11/16 / 2023.11.16
    re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}"),    # 16/11/2023
)
DATE_PLACEHOLDER_FMT = "[[DATE_{}]]"

DATE_COMBINED_RE = re.compile("|".join(f"(?:{r.pattern})" for r in DATE_RES))


def normalize_dates(text: str) -> tuple[str, dict[str, str]]:
    """数字型日期 → [[DATE_n]] 占位符；返回 (归一文本, {占位符: 原日期})。"""
    mapping: dict[str, str] = {}

    def _sub(match: re.Match) -> str:
        placeholder = DATE_PLACEHOLDER_FMT.format(len(mapping) + 1)
        mapping[placeholder] = match.group(0)
        return placeholder

    return DATE_COMBINED_RE.sub(_sub, text), mapping
