"""CommOCR 模版移植校验：转换映射正确 + 可入模版库 + 幂等。

覆盖 CommOCR templates.json（2026-09-07）→ CommAND 模版库的忠实转换：
postprocess→hooks、lenient_fields→lenient、model/skip_text_pdf→级联默认值。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from seed_ocr_templates import TEMPLATES  # noqa: E402

from command_shared.ocr_templates import TemplateStore  # noqa: E402

MIGRATED = {t["id"]: t for t in TEMPLATES if t.get("source_id")}


def test_migrated_set():
    assert set(MIGRATED) == {"tpl.invoice.english", "tpl.custom.blueprint", "tpl.contract.table"}


def _seeded(tmp_path):
    store = TemplateStore(str(tmp_path))
    for tpl in TEMPLATES:
        store.upsert(tpl)
    return store


def test_all_six_seedable(tmp_path):
    store = _seeded(tmp_path)
    ids = {it["id"] for it in store.list()}
    assert ids == {
        "tpl.invoice.voucher", "tpl.contract.history", "tpl.audit.shenbao",
        "tpl.invoice.english", "tpl.custom.blueprint", "tpl.contract.table",
    }
    assert store.get("tpl.invoice.voucher")["name"] == "01识别发票凭证"
    assert store.get("tpl.audit.shenbao")["name"] == "07识别决算审定表"


def test_english_doc_mapping(tmp_path):
    t = _seeded(tmp_path).get("tpl.invoice.english")
    assert t["name"] == "04识别英文单据" and t["category"] == "invoice"
    assert (len(t["fields"]), len(t["rules"]), len(t["hooks"])) == (30, 14, 3)
    assert t["record_mode"] == "page" and t["lenient"] is False
    props = t["input_schema"]["properties"]
    assert props["model"]["default"] == "qwen-vl-max"
    assert props["skip_text_pdf"]["default"] is True


def test_blueprint_and_contract_table_mapping(tmp_path):
    bp = _seeded(tmp_path).get("tpl.custom.blueprint")
    assert (bp["name"], bp["category"]) == ("05识别平面布置", "custom")
    assert bp["lenient"] is True and len(bp["hooks"]) == 5 and len(bp["fields"]) == 16

    ct = _seeded(tmp_path).get("tpl.contract.table")
    assert (ct["name"], ct["category"]) == ("06合同表格识别", "contract")
    assert ct["lenient"] is True and len(ct["rules"]) == 10 and len(ct["hooks"]) == 3


def test_hooks_carry_code():
    for t in MIGRATED.values():
        for hook in t["hooks"]:
            assert hook.get("code"), f"{t['id']} hook missing code"


def test_seed_idempotent(tmp_path):
    store = TemplateStore(str(tmp_path))
    for tpl in TEMPLATES:
        assert store.upsert(tpl)["status"] == "created"
    for tpl in TEMPLATES:
        assert store.upsert(tpl)["status"] == "updated"
