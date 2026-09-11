"""翻译模版种子（translee 体验还原 T1）：内置「默认 / 审计财务」两个模版。

来源：translee templates.json（语言对 + 术语表 + 模型）。幂等 upsert，重复执行安全。
用法：uv run python scripts/seed_translate_templates.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from command_shared.translate_templates import TranslateTemplateStore  # noqa: E402

TEMPLATES: list[dict] = [
    {
        "id": "default",
        "name": "通用英译中",
        "desc": "",
        "source_lang": "English",
        "target_lang": "Chinese",
        "model": "",
        "terms": [],
    },
    {
        "id": "audit",
        "name": "审计财务",
        "desc": "财务报表/审计底稿常用术语表",
        "source_lang": "English",
        "target_lang": "Chinese",
        "model": "",
        "terms": [
            ["Audited Financial Statements", "审计后财务报表"],
            ["Statement of Financial Position", "财务状况表"],
            ["Notes to the Financial Statements", "财务报表附注"],
            ["Going Concern", "持续经营"],
            ["Internal Control over Financial Reporting", "财务报告内部控制"],
            ["Management Representation Letter", "管理层声明书"],
            ["Subsequent Events", "期后事项"],
            ["Related Party Transactions", "关联方交易"],
        ],
    },
]


def main() -> None:
    store = TranslateTemplateStore(os.environ.get("COMMAND_DATA_DIR") or None)
    for tpl in TEMPLATES:
        action = "更新" if store.exists(tpl["id"]) else "新增"
        store.upsert(tpl)
        print(f"[{action}] {tpl['id']}（{tpl['name']}，{len(tpl['terms'])} 条术语）")
    print(f"完成：{len(TEMPLATES)} 个翻译模版就绪 @ "
          f"{os.environ.get('COMMAND_DATA_DIR', 'data')}/translate/templates/")


if __name__ == "__main__":
    main()
