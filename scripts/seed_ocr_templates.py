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

# ── 模版级联表单的系统参数（X1：所有模版共享，单一定义防漂移）─────────────────
# key_name 原标题「记录主键名」是语义错标：它实际是 img.vl.extract 的命名密钥参数，
# 伪默认值（voucher/contract/…）会触发「密钥不存在」暂停 —— 已废除默认值、改为密钥下拉。
SYSTEM_PARAMS: dict = {
    "key_name": {
        "type": ["string", "null"], "title": "识别密钥", "format": "keys",
        "description": "留空用默认",
    },
    "auto_rotate": {
        "type": ["boolean", "null"], "title": "自动转正",
        "default": True,
        "description": "歪页自动回正",
    },
    "export_units": {
        "type": ["boolean", "null"], "title": "导出识别单元",
        "default": False,
        "description": "识别完成后提取记录单元（供后续翻译链使用）；仅识别不需要开启",
    },
    # AP-B：页级缓存命中时不会重识别；改过模版/规则后想拿新结果就勾这个（强制全量重跑）
    "force": {
        "type": ["boolean", "null"], "title": "重新识别（忽略已有结果）",
        "default": False,
        "description": "清掉该文件在本库的旧结果再全量识别；改过模版/规则后用，平时关闭可命中页级缓存省钱",
    },
    # AA2：上游 qwen-vl-max 滚动快照对密集多行表格出现「只吐第一行」行为漂移，
    # 提供快照切换做对照试验/临时规避；留空走引擎默认（qwen-vl-max）。
    "model": {
        "type": ["string", "null"], "title": "多模态模型",
        "examples": ["qwen-vl-max", "qwen-vl-plus"],
        "default": None,
        "description": "留空用默认模型（qwen-vl-max）；候选 qwen-vl-max / qwen-vl-plus，也可填官方具体快照名（如 qwen-vl-max-2025-01-25）固定版本规避滚动更新行为变化",
    },
}


def _with_system_params(tpl: dict) -> dict:
    """把系统参数并入模版 input_schema（模版自有同名键优先，避免覆盖调优值）。"""
    props = dict(SYSTEM_PARAMS)
    own = (tpl.get("input_schema") or {}).get("properties") or {}
    props.update(own)
    out = dict(tpl)
    out["input_schema"] = {"type": "object", "properties": props}
    return out


def _raw_templates() -> list[dict]:
    return [
        {
            "id": "tpl.invoice.voucher", "name": "01识别发票凭证", "category": "invoice",
            "prompt_template": VOUCHER_TEMPLATE, "fields": VOUCHER_FIELDS,
            "rules": VOUCHER_RULES, "example": VOUCHER_EXAMPLE,
            "hooks": [{"name": "凭证金额校验与大写兜底", "code": VOUCHER_POSTPROCESS_CODE}],
            "record_mode": "page", "lenient": False,
        },
        {
            "id": "tpl.contract.history", "name": "02识别历史合同", "category": "contract",
            "prompt_template": CONTRACT_TEMPLATE, "fields": CONTRACT_FIELDS,
            "hooks": [], "record_mode": "page", "lenient": False,
            "input_schema": {
                "type": "object",
                "properties": {
                    "skip_text_pdf": {"type": ["boolean", "null"], "title": "文本层直读", "default": False,
                                      "description": "文本 PDF 跳过视觉识别"},
                },
            },
        },
        {
            "id": "tpl.audit.shenbao", "name": "07识别决算审定表", "category": "audit",
            "prompt_template": SHENBAO_TEMPLATE, "fields": SHENBAO_FIELDS,
            "rules": SHENBAO_RULES, "example": SHENBAO_EXAMPLE,
            "hooks": [{"name": "审定表金额归一与勾稽校验", "code": SHENBAO_POSTPROCESS_CODE}],
            "record_mode": "page", "lenient": True,
        },
    ]


# ── CommOCR 用户模版移植（04 英文单据 / 05 平面布置 / 06 合同表格）──────────────
# 变量名 → (模版库 id, category)
_COMMOCR_MAP = {
    "ENGLISH_DOC": ("tpl.invoice.english", "invoice"),
    "BLUEPRINT": ("tpl.custom.blueprint", "custom"),
    "CONTRACT_TABLE": ("tpl.contract.table", "contract"),
}


def _from_commocr(var: str, data: dict) -> dict:
    tid, category = _COMMOCR_MAP[var]
    props: dict = {}
    if data.get("model"):
        props["model"] = {"type": ["string", "null"], "title": "多模态模型", "default": data["model"]}
    if data.get("skip_text_pdf") is not None:
        props["skip_text_pdf"] = {"type": ["boolean", "null"], "title": "文本层直读",
                                  "default": bool(data["skip_text_pdf"]), "description": "文本 PDF 跳过视觉识别"}
    return {
        "id": tid, "name": data["name"], "category": category, "source_id": data["source_id"],
        "prompt_template": data["prompt_template"], "fields": data["fields"],
        "rules": data.get("rules"), "example": data.get("example"),
        "hooks": data.get("postprocess") or [],
        "record_mode": "page", "lenient": bool(data.get("lenient")),
        "input_schema": {"type": "object", "properties": props},
    }


TEMPLATES = [_with_system_params(t) for t in (_raw_templates()
                                              + [_from_commocr(var, data) for var, data in COMMOCR_USER_TEMPLATES])]


def main() -> None:
    store = TemplateStore()
    for tpl in TEMPLATES:
        existed = True
        try:
            store.get(tpl["id"])
        except Exception:
            existed = False
        # X1：种子里模版自有键优先（保调优值），系统参数以代码为准刷新（保语义/标题正确）
        result = store.upsert(_with_system_params(tpl))
        print(f"[{'更新' if existed else '新增'}] {tpl['id']} ({result['status']})")
    print(f"完成：{len(TEMPLATES)} 个模版就绪 @ {os.environ.get('COMMAND_DATA_DIR', 'data')}/ocr/templates/")


if __name__ == "__main__":
    main()
