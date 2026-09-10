"""E1 识别规则模版库单测：存取/校验/启停/删除/损坏容错（tmp 目录，不碰真实 data/）。"""

import json

import pytest

from command_shared.ocr_templates import TemplateStore
from core.errors import ToolDomainError, ToolNotFoundError


@pytest.fixture
def store(tmp_path):
    return TemplateStore(str(tmp_path))


def _valid(tid="tpl.demo", category="invoice", **kw):
    return {"id": tid, "name": "演示模版", "category": category,
            "prompt_template": "请识别{field_count}个字段：{fields}",
            "fields": ["金额", "日期"], "hooks": [], **kw}


def test_upsert_create_update_roundtrip(store):
    assert store.upsert(_valid())["status"] == "created"
    item = store.get("tpl.demo")
    assert item["category"] == "invoice" and item["enabled"] is True
    assert item["created_at"] == item["updated_at"]

    store.upsert(_valid(name="改名"))
    item = store.get("tpl.demo")
    assert item["name"] == "改名"
    assert item["created_at"] <= item["updated_at"]  # 创建时间保留


def test_upsert_validation(store):
    with pytest.raises(ToolDomainError, match="id"):
        store.upsert(_valid(tid="X"))  # 大写不符 id 规则
    with pytest.raises(ToolDomainError, match="category"):
        store.upsert(_valid(category="bogus"))
    with pytest.raises(ToolDomainError, match="fields"):
        store.upsert(_valid(fields=[]))
    with pytest.raises(ToolDomainError, match="prompt_template"):
        store.upsert(_valid(prompt_template="   "))
    # 无 {fields} 占位合法（合同类固定提示词，渲染时占位符无为）
    store.upsert(_valid(prompt_template="固定提示词", tid="tpl.nofield"))
    assert store.get("tpl.nofield")["prompt_template"] == "固定提示词"
    with pytest.raises(ToolDomainError, match="record_mode"):
        store.upsert(_valid(record_mode="bogus"))


def test_set_enabled_toggle_and_list_filter(store):
    store.upsert(_valid())
    store.upsert(_valid(tid="tpl.two", category="contract", name="合同模版"))
    store.set_enabled("tpl.two", False)
    assert store.get("tpl.two")["enabled"] is False

    assert [t["id"] for t in store.list(enabled=True)] == ["tpl.demo"]
    assert [t["id"] for t in store.list(enabled=False)] == ["tpl.two"]
    assert [t["id"] for t in store.list(category="contract")] == ["tpl.two"]
    assert [t["id"] for t in store.list(keyword="演示")] == ["tpl.demo"]


def test_delete_and_missing(store):
    store.upsert(_valid())
    assert store.delete("tpl.demo")["status"] == "deleted"
    with pytest.raises(ToolNotFoundError):
        store.get("tpl.demo")
    with pytest.raises(ToolNotFoundError):
        store.delete("tpl.demo")
    with pytest.raises(ToolNotFoundError):
        store.get("tpl.ghost")


def test_corrupt_file_skipped_in_list(store, tmp_path):
    store.upsert(_valid())
    (tmp_path / "ocr" / "templates" / "tpl.bad.json").write_text("{broken", encoding="utf-8")
    items = store.list()
    assert [t["id"] for t in items] == ["tpl.demo"]  # 损坏条目跳过不炸
    assert json.loads((tmp_path / "ocr" / "templates" / "tpl.demo.json").read_text(encoding="utf-8"))["id"] == "tpl.demo"
