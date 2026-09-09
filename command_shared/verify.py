"""质检层：数字保真 / 占位符保真 / 空值截断 / 无字母恒等 / 英文残留——不合格进重译队列。

移植自 translee verify.py（含真实联调沉淀的污染防御规则）。
"""
from __future__ import annotations

import re

_DIGITS_RE = re.compile(r"\d+")
_PLACEHOLDER_RE = re.compile(r"\[\[DATE_\d+\]\]")
_HAS_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_EN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

VERIFY_MIN_RATIO = 0.3  # 译文长度 < 原文 30% 判截断（仅对 ≥60 字符原文生效）


def is_code_like(text: str) -> bool:
    """编号/纯数字判定：不可译，直存原文省一次 API 调用。

    规则（宁漏勿杀：拿不准的一律送去翻译）：
    - 去空白后无任何字母 → 纯数字/符号（2644 / 3361.215 / 141002401003677）
    - 无空白、字母全大写、含 ≥2 位数字、总长 ≥8 → 编号串（PO202004291012 / KTD2V79R-D6）
    """
    s = text.strip()
    if not s:
        return False
    if not any(c.isalpha() for c in s):
        return True
    if any(c.isspace() for c in s):
        return False
    letters = [c for c in s if c.isalpha()]
    digits = sum(c.isdigit() for c in s)
    return digits >= 2 and len(s) >= 8 and all(c.isupper() for c in letters)


def verify_pair(source: str, translated: str) -> tuple[bool, str]:
    """校验一条译文；返回 (合格?, 失败原因)。空译文按原文原样通过。

    规则：
    1. 数字保真——原文全部数字串必须出现在译文中
    2. 占位符保真——[[DATE_n]] 必须原样保留（回填阶段回插日期）
    3. 无字母恒等——纯数字/编号原文译文必须与原文一致
    4. 空值/截断——译文为空，或长度 < 原文 30%（仅对 ≥60 字符原文生效）
    5. 英文残留——原文多词英文，译文却无中文字符且英文词基本没减少：判未翻译
    """
    src = (source or "").strip()
    dst = (translated or "").strip()
    if not src:
        return True, ""
    if not dst:
        if src == translated:  # 原文本身为空串/空白
            return True, ""
        return False, "empty"
    for placeholder in set(_PLACEHOLDER_RE.findall(src)):
        if placeholder not in dst:
            return False, f"missing_placeholder:{placeholder}"
    for number in set(_DIGITS_RE.findall(_PLACEHOLDER_RE.sub("", src))):
        if number not in dst:
            return False, f"missing_number:{number}"
    if not _HAS_LETTER_RE.search(src) and dst != src:
        return False, "not_identical"
    src_words = _EN_WORD_RE.findall(src)
    if len(src_words) >= 2 and not _CJK_RE.search(dst):
        if len(_EN_WORD_RE.findall(dst)) >= max(2, int(len(src_words) * 0.6)):
            return False, "untranslated"
    if len(src) >= 60 and len(dst) < len(src) * VERIFY_MIN_RATIO:
        return False, "truncated"
    return True, ""


def retranslate_prompt(source: str, reason: str) -> str:
    """重译失败条目时的强化指令。"""
    hint = {
        "empty": "The previous translation was empty.",
        "truncated": "The previous translation was truncated. Translate the complete text.",
        "not_identical": "The source contains no translatable words. Output it unchanged, character for character.",
        "missing_number": "The previous translation is missing numbers that appear in the source. Keep ALL numbers exactly as in the source.",
        "missing_placeholder": "The previous translation lost a placeholder like [[DATE_1]]. Keep every placeholder exactly as in the source.",
        "untranslated": "The text was left untranslated. Translate ALL of it into Chinese, including company names, addresses and headings. Keep only real codes/IDs unchanged.",
    }.get(reason.split(":")[0], "")
    return f"{hint}\nSource: {source}" if hint else source
