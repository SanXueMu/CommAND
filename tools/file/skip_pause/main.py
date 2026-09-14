"""刻意跳过并暂停（如暂不支持的 PPT）。

用暂停（而非失败或静默忽略）表达「这批里这个文件本轮不处理」：
任务落 paused、在清单里可见可决策；源文件由批次清单保证随导出一起交付。
若之后要处理，把文件换成受支持格式再点「继续」即可。
"""
from __future__ import annotations


def run(input: dict, ctx, emit) -> dict:
    from core.errors import ToolPauseError

    reason = str(input.get("reason") or "").strip() or "该文件本轮不处理（暂不支持的类型）"
    emit({"phase": "skipped", "file": input.get("file"), "reason": reason})
    raise ToolPauseError(
        reason,
        hint="如需翻译：转成受支持格式后重新上传；本文件会以原文件形式随批次一并导出",
    )
