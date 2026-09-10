"""E3 模版种子：把 CommOCR 三内置模版灌入识别模版库（data/ocr/templates/），幂等。

用法：uv run python scripts/seed_ocr_templates.py
模版数据来自 ocr_builtin_templates.py（CommOCR builtin_templates.py 原样拷贝）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from ocr_builtin_templates import (  # noqa: E402
    CONTRACT_FIELDS, CONTRACT_TEMPLATE, SHENBAO_FIELDS, SHENBAO_TEMPLATE,
    SHENBAO_RULES, SHENBAO_EXAMPLE, SHENBAO_POSTPROCESS_CODE,
    VOUCHER_FIELDS, VOUCHER_TEMPLATE, VOUCHER_RULES, VOUCHER_EXAMPLE,
    VOUCHER_POSTPROCESS_CODE,
)
from command_shared.ocr_templates import TemplateStore  # noqa: E402

TEMPLATES = [
    {
        "id": "tpl.invoice.voucher", "name": "发票凭证识别", "category": "invoice",
        "prompt_template": VOUCHER_TEMPLATE, "fields": VOUCHER_FIELDS,
        "rules": VOUCHER_RULES, "example": VOUCHER_EXAMPLE,
        "hooks": [{"name": "凭证金额校验与大写兜底", "code": VOUCHER_POSTPROCESS_CODE}],
        "record_mode": "page", "lenient": False,
    },
    {
        "id": "tpl.contract.history", "name": "历史合同识别", "category": "contract",
        "prompt_template": CONTRACT_TEMPLATE, "fields": CONTRACT_FIELDS,
        "hooks": [], "record_mode": "page", "lenient": False,
    },
    {
        "id": "tpl.audit.shenbao", "name": "决算审定表识别", "category": "audit",
        "prompt_template": SHENBAO_TEMPLATE, "fields": SHENBAO_FIELDS,
        "rules": SHENBAO_RULES, "example": SHENBAO_EXAMPLE,
        "hooks": [{"name": "审定表金额归一与勾稽校验", "code": SHENBAO_POSTPROCESS_CODE}],
        "record_mode": "page", "lenient": True,
    },
]


def main() -> None:
    store = TemplateStore()
    for tpl in TEMPLATES:
        existed = True
        try:
            store.get(tpl["id"])
        except Exception:
            existed = False
        result = store.upsert(tpl)
        print(f"[{'更新' if existed else '新增'}] {tpl['id']} ({result['status']})")
    print(f"完成：{len(TEMPLATES)} 个内置模版就绪 @ {os.environ.get('COMMAND_DATA_DIR', 'data')}/ocr/templates/")


if __name__ == "__main__":
    main()
