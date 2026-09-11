"""E3 模版种子：把 CommOCR 模版灌入识别模版库（data/ocr/templates/），幂等。

用法：uv run python scripts/seed_ocr_templates.py
模版数据来自两处（均为 git 追踪、可复现部署）：
  - ocr_builtin_templates.py：CommOCR 三内置模版（voucher/contract/shenbao）
  - commocr_templates.py：CommOCR 用户模版移植（04 英文单据 / 05 平面布置 / 06 合同表格）
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
from commocr_templates import COMMOCR_USER_TEMPLATES  # noqa: E402
from command_shared.ocr_templates import TemplateStore  # noqa: E402

TEMPLATES = [
    {
        "id": "tpl.invoice.voucher", "name": "01识别发票凭证", "category": "invoice",
        "prompt_template": VOUCHER_TEMPLATE, "fields": VOUCHER_FIELDS,
        "rules": VOUCHER_RULES, "example": VOUCHER_EXAMPLE,
        "hooks": [{"name": "凭证金额校验与大写兜底", "code": VOUCHER_POSTPROCESS_CODE}],
        "record_mode": "page", "lenient": False,
        # I2：模版增量输入声明（级联表单数据源）——选模版后表单随之变化
        "input_schema": {
            "type": "object",
            "properties": {"key_name": {"type": "string", "title": "记录主键名", "default": "voucher"}},
        },
    },
    {
        "id": "tpl.contract.history", "name": "02识别历史合同", "category": "contract",
        "prompt_template": CONTRACT_TEMPLATE, "fields": CONTRACT_FIELDS,
        "hooks": [], "record_mode": "page", "lenient": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "key_name": {"type": "string", "title": "记录主键名", "default": "contract"},
                "skip_text_pdf": {"type": "boolean", "title": "文本层PDF直读", "default": False,
                                   "description": "历史合同扫描件建议关闭"},
            },
        },
    },
    {
        "id": "tpl.audit.shenbao", "name": "07识别决算审定表", "category": "audit",
        "prompt_template": SHENBAO_TEMPLATE, "fields": SHENBAO_FIELDS,
        "rules": SHENBAO_RULES, "example": SHENBAO_EXAMPLE,
        "hooks": [{"name": "审定表金额归一与勾稽校验", "code": SHENBAO_POSTPROCESS_CODE}],
        "record_mode": "page", "lenient": True,
        "input_schema": {
            "type": "object",
            "properties": {"key_name": {"type": "string", "title": "记录主键名", "default": "shenbao"}},
        },
    },
]


# ── CommOCR 用户模版移植（04 英文单据 / 05 平面布置 / 06 合同表格）──────────────
# 变量名 → (模版库 id, category, key_name 默认值)
_COMMOCR_MAP = {
    "ENGLISH_DOC": ("tpl.invoice.english", "invoice", "english"),
    "BLUEPRINT": ("tpl.custom.blueprint", "custom", "blueprint"),
    "CONTRACT_TABLE": ("tpl.contract.table", "contract", "contract_table"),
}


def _from_commocr(var: str, data: dict) -> dict:
    tid, category, key_name = _COMMOCR_MAP[var]
    props: dict = {"key_name": {"type": "string", "title": "记录主键名", "default": key_name}}
    if data.get("model"):
        props["model"] = {"type": "string", "title": "多模态模型", "default": data["model"]}
    if data.get("skip_text_pdf") is not None:
        props["skip_text_pdf"] = {"type": "boolean", "title": "文本层PDF直读",
                                  "default": bool(data["skip_text_pdf"])}
    return {
        "id": tid, "name": data["name"], "category": category, "source_id": data["source_id"],
        "prompt_template": data["prompt_template"], "fields": data["fields"],
        "rules": data.get("rules"), "example": data.get("example"),
        "hooks": data.get("postprocess") or [],
        "record_mode": "page", "lenient": bool(data.get("lenient")),
        "input_schema": {"type": "object", "properties": props},
    }


TEMPLATES += [_from_commocr(var, data) for var, data in COMMOCR_USER_TEMPLATES]


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
    print(f"完成：{len(TEMPLATES)} 个模版就绪 @ {os.environ.get('COMMAND_DATA_DIR', 'data')}/ocr/templates/")


if __name__ == "__main__":
    main()
