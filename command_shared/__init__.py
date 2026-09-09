"""command_shared——CommAND 工具共享库（无状态纯函数 + LLM 客户端工厂）。

库复用 ≠ 工具耦合：本包只提供无状态能力，不感知任何工具的业务语义；
inproc 工具与 CommAND 同进程运行，直接 `from command_shared import ...`。
"""

from command_shared.chat import TranslationError, call_chat, make_client, merge_usage
from command_shared.normalize import normalize_dates
from command_shared.verify import is_code_like, retranslate_prompt, verify_pair

__all__ = [
    "TranslationError",
    "call_chat",
    "make_client",
    "merge_usage",
    "normalize_dates",
    "is_code_like",
    "retranslate_prompt",
    "verify_pair",
]
