"""翻译域端点单测：翻译模版 CRUD + 已译字典浏览（tmp 目录，不碰真实 data/）。"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from api import translate_router as router  # noqa: E402
from command_shared import dict_cache  # noqa: E402
from core.errors import ToolDomainError, ToolNotFoundError  # noqa: E402
from seed_translate_templates import TEMPLATES  # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    return tmp_path


def test_seed_templates_upsert_and_list(data_dir):
    store = router._store()
    for tpl in TEMPLATES:
        store.upsert(tpl)
    items = router.list_templates()["templates"]
    assert {i["id"] for i in items} == {"default", "audit"}
    audit = router.get_template("audit")
    assert audit["name"] == "审计财务"
    assert len(audit["terms"]) == 8
    assert audit["terms"][0] == ["Audited Financial Statements", "审计后财务报表"]
    assert audit["source_lang"] == "English" and audit["target_lang"] == "Chinese"


def test_upsert_validation(data_dir):
    store = router._store()
    with pytest.raises(ToolDomainError):
        store.upsert({"id": "Bad", "name": "x", "source_lang": "en", "target_lang": "zh"})
    with pytest.raises(ToolDomainError):
        store.upsert({"id": "ok.id", "name": "", "source_lang": "en", "target_lang": "zh"})
    with pytest.raises(ToolDomainError):
        store.upsert({"id": "ok.id", "name": "n", "source_lang": "en", "target_lang": "zh",
                      "terms": [["a"]]})


def test_upsert_idempotent_and_delete(data_dir):
    store = router._store()
    first = store.upsert({"id": "x.y", "name": "N1", "source_lang": "en", "target_lang": "zh"})
    assert first["status"] == "created"
    again = store.upsert({"id": "x.y", "name": "N2", "source_lang": "en", "target_lang": "zh"})
    assert again["status"] == "updated"
    assert store.get("x.y")["name"] == "N2"
    assert store.delete("x.y")["status"] == "deleted"
    with pytest.raises(ToolNotFoundError):
        store.get("x.y")


def test_dict_browse_filter_paging_stats(data_dir):
    conn = dict_cache.open_dict()
    try:
        for i, (src, tgt, status, model) in enumerate([
            ("Going Concern", "持续经营", "ok", "qwen"),
            ("Subsequent Events", "期后事项", "review", "qwen"),
            ("Total Assets", "资产总额", "ok", "deepseek"),
        ]):
            dict_cache.save(conn, f"k{i}", src, tgt, model=model, status=status)
    finally:
        conn.close()

    out = router.browse_dict(limit=50)
    assert out["total"] == 3
    assert out["stats"]["ok"] == 2 and out["stats"]["review"] == 1
    assert set(out["models"]) == {"qwen", "deepseek"}

    only_review = router.browse_dict(status="review")
    assert only_review["total"] == 1 and only_review["rows"][0]["source"] == "Subsequent Events"

    searched = router.browse_dict(q="资产")
    assert searched["total"] == 1 and searched["rows"][0]["translated"] == "资产总额"

    paged = router.browse_dict(limit=2, offset=0)
    assert len(paged["rows"]) == 2 and paged["total"] == 3


def test_llm_translate_terms_schema_accepts_string_and_array():
    """术语表入参：flow 级声明为字符串（textarea），工具 _parse_terms 兼容字符串；
    schema 必须同时接受 array 与 string，否则工作台运行时报 $.terms 校验失败。"""
    import json

    import jsonschema

    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "tools/text/llm_translate/input.schema.json")
        .read_text(encoding="utf-8")
    )
    base = {"segments": ["Audit Report"]}
    jsonschema.validate({**base, "terms": "Audit Report => 审计报告"}, schema)
    jsonschema.validate({**base, "terms": [["Audit Report", "审计报告"]]}, schema)
    jsonschema.validate(base, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "terms": 123}, schema)
