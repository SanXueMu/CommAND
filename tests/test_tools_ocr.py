"""OCR 域 8 工具 + command_shared OCR 引擎测试。

fake VL 客户端按提示词内容返回 canned JSON；PDF 用 fitz 现做。
语义锁定：解析严格/宽松、钩子注记、缓存断点、熔断记账、视图四模式、跨页合并。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import fitz
import pytest

from command_shared import ocr_engine, ocr_storage
from command_shared.ocr_validate import HookError, compile_page_hook, parse_records, run_page_hooks
from command_shared.ocr_views import ViewSpec, compute_view
from core.errors import ToolDomainError


# ---------- fakes ----------

class FakeVLClient:
    """按调用序返回 canned 应答；可注入异常序列。"""

    def __init__(self, replies: list[str], errors: list[Exception] | None = None):
        self.replies = list(replies)
        self.errors = list(errors or [])
        self.calls: list[str] = []

    def chat(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.errors:
            raise self.errors.pop(0)
        return self.replies.pop(0) if self.replies else "[]"


DEFAULT_KEYS = {"dashscope": {"provider": "dashscope", "api_key": "sk-test",
                              "is_default": True}}


class FakeCtx:
    def __init__(self, keys: dict | None = None):
        self.keys = DEFAULT_KEYS if keys is None else keys


def _emit_collector():
    events: list[dict] = []
    return events, (lambda event: events.append(event))


def _pdf(path, pages: int = 2, rotate_text: bool = False) -> str:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        if rotate_text:
            page.insert_text((100, 500), f"第{index + 1}页横排内容", rotate=90)
        else:
            page.insert_text((72, 72), f"第{index + 1}页内容 金额：100 元")
    doc.save(path)
    doc.close()
    return str(path)


# ---------- ocr_validate ----------

def test_parse_records_strict_and_lenient():
    raw = '```json\n[{"发票号": "123", "金额": "100"}, {"发票号": "456"}]\n```'
    assert parse_records(raw, ["发票号", "金额"], None) == [
        {"发票号": "123", "金额": "100"}]  # 严格：缺金额记录丢弃
    assert parse_records(raw, ["发票号", "金额"], ["金额"]) == [
        {"发票号": "123", "金额": "100"}, {"发票号": "456", "金额": ""}]


def test_parse_records_bad_json_raises():
    # 宽松只放宽字段缺席，不放宽 JSON 合法性——坏应答按页失败（重跑续扫兜底）
    with pytest.raises(ValueError):
        parse_records("完全不是JSON", ["字段"], ["字段"])


def test_hook_compile_and_run():
    code = (
        "def transform_page(records, ctx):\n"
        "    for rec in records:\n"
        "        if not rec.get('金额'):\n"
        "            ctx['review']('金额缺失待审')\n"
        "            rec['金额'] = '0'\n"
        "        else:\n"
        "            rec['金额'] = rec['金额'].replace('元', '')\n"
        "    return records\n"
    )
    hook = {"name": "amount", "fn": compile_page_hook("amount", code)}
    out = run_page_hooks([hook], [{"金额": "100元"}], 1, ["金额"])
    assert out == [{"金额": "100"}]
    notes: list[str] = []
    out = run_page_hooks([hook], [{"金额": ""}], 2, ["金额"], notes.append)
    assert out == [{"金额": "0"}]
    assert notes == ["金额缺失待审"]


def test_hook_compile_rejects_bad_code():
    with pytest.raises(HookError):
        compile_page_hook("bad", "this is not python")


def test_hook_requires_transform_page():
    with pytest.raises(HookError):
        compile_page_hook("old_style", "def page_hook(fields, add_note):\n    pass")


# ---------- ocr_storage ----------

def test_storage_roundtrip_and_breakpoint(tmp_path):
    connection = ocr_storage.connect(tmp_path / "t.db")
    ocr_storage.initialize(connection)
    written = ocr_storage.append_records(
        connection, "hash1", "a.pdf",
        [(1, {"发票号": "1", "页码": 1}), (2, {"发票号": "2", "页码": 2})])
    assert written == 2
    # OR IGNORE 首写为准：同 (hash, path, row) 重写被忽略，返回真实新增 0
    written = ocr_storage.append_records(
        connection, "hash1", "a.pdf", [(2, {"发票号": "2", "页码": 2})])
    assert written == 0
    assert set(ocr_storage.get_cached_rows(connection, "hash1", "a.pdf")) == {1, 2}
    assert len(ocr_storage.read_records(connection, "hash1", "a.pdf")) == 2
    connection.close()


# ---------- ocr_views ----------

def _rows():
    return [
        (1, {"合同名称线索": "施工合同A", "金额": "100万", "页码": 1}),
        (2, {"合同名称线索": "施工合同A", "关键人物出现方式": "项目负责人签字", "类型线索": "施工", "页码": 2}),
        (3, {"关键人物出现方式": "项目负责人", "页码": 3}),  # 线索缺席 → 归前段
        (4, {"合同名称线索": "采购合同B", "页码": 4}),
    ]


def test_view_value_run_and_verdict():
    spec = ViewSpec(**{
        "name": "t",
        "group": {"mode": "value_run", "field": "合同名称线索"},
        "aggregates": [
            {"column": "合同名称", "op": "group_key"},
            {"column": "起始页", "op": "page_start"},
            {"column": "页数", "op": "page_count"},
            {"column": "证据", "op": "evidence", "field": "关键人物出现方式"},
        ],
        "verdict": {"column": "判定",
                    "rules": [{"label": "命中", "when": {"all": [
                        {"field": "关键人物出现方式", "op": "nonempty"}]}}],
                    "default": "不匹配"},
    })
    result = compute_view(_rows(), spec)
    assert [row["合同名称"] for row in result["rows"]] == ["施工合同A", "采购合同B"]
    assert result["rows"][0]["起始页"] == 1 and result["rows"][0]["页数"] == 3
    assert result["rows"][0]["判定"] == "命中" and result["rows"][1]["判定"] == "不匹配"
    assert "第2页" in result["rows"][0]["证据"]


def test_view_record_mode_and_filters():
    spec = ViewSpec(**{
        "group": {"mode": "record"},
        "filters": [{"field": "金额", "op": "nonempty"}],
        "aggregates": [{"column": "金额", "op": "first_value"},
                       {"column": "页码", "op": "page"}],
    })
    result = compute_view(_rows(), spec)
    assert len(result["rows"]) == 1 and result["rows"][0]["金额"] == "100万"


def test_view_split_tables():
    spec = ViewSpec(**{
        "group": {"mode": "none"},
        "aggregates": [{"column": "金额", "op": "first_value"}],
        "split": {"field": "表格名称"},
    })
    rows = [(1, {"表格名称": "决算表", "金额": "5", "页码": 1}),
            (1, {"表格名称": "明细表", "金额": "6", "页码": 1}),
            (2, {"表格名称": "决算表", "金额": "", "页码": 2})]
    result = compute_view(rows, spec)
    assert {s["key"] for s in result["splits"]} == {"决算表", "明细表"}


# ---------- ocr_engine（page 模式 fake 客户端） ----------

def test_engine_page_mode_and_breakpoint(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path / "doc.pdf", pages=2)
    db = tmp_path / "out.db"
    connection = ocr_storage.connect(db)
    ocr_storage.initialize(connection)

    replies = iter([
        json.dumps([{"发票号": "A1", "金额": "100"}], ensure_ascii=False),
        json.dumps([{"发票号": "A2", "金额": "200"}], ensure_ascii=False),
    ])
    monkeypatch.setattr(ocr_engine, "call_vl", lambda *a, **k: next(replies))
    stats = ocr_engine.process_document(
        pdf, connection, object(), "prompt", ["发票号", "金额"], model="qwen-vl-max",
        skip_text_pdf=False, page_concurrency=1)
    assert stats["pages_done"] == 2 and stats["failed_pages"] == []
    records = ocr_storage.read_records(connection, stats["file_hash"], "doc.pdf")
    assert {r["发票号"] for r in records} == {"A1", "A2"}

    # 断点续跑：全部页已缓存 → 零调用
    stats2 = ocr_engine.process_document(
        pdf, connection, object(), "prompt", ["发票号", "金额"], model="m",
        skip_text_pdf=False)
    assert stats2["pages_cached"] == 2 and stats2["pages_done"] == 0
    connection.close()


def test_engine_hooks_and_circuit(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path / "doc.pdf", pages=3)
    connection = ocr_storage.connect(tmp_path / "o.db")
    ocr_storage.initialize(connection)
    hook_code = "def transform_page(records, ctx):\n    ctx['review']('checked')\n    return records\n"
    hook = {"name": "t", "code": hook_code}

    monkeypatch.setattr(ocr_engine, "call_vl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    stats = ocr_engine.process_document(
        pdf, connection, object(), "p", ["发票号"], model="m",
        postprocess=[hook], skip_text_pdf=False, page_concurrency=1, fail_circuit=2)
    assert stats["records_written"] == 0
    assert len(stats["failed_pages"]) == 2  # 熔断在第 2 次连续失败
    connection.close()


def test_engine_record_mode_merges(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path / "doc.pdf", pages=2)
    connection = ocr_storage.connect(tmp_path / "o.db")
    ocr_storage.initialize(connection)
    replies = iter([
        json.dumps([{"内容": "首页内容", "金额": "100"}], ensure_ascii=False),
        json.dumps([{"内容": "尾页内容", "金额": "100"}], ensure_ascii=False),  # 金额重复去重
    ])
    monkeypatch.setattr(ocr_engine, "call_vl", lambda *a, **k: next(replies))
    stats = ocr_engine.process_document(
        pdf, connection, object(), "p", ["内容", "金额"], model="m",
        record_mode="record", skip_text_pdf=False)
    records = ocr_storage.read_records(connection, stats["file_hash"], "doc.pdf")
    assert len(records) == 1
    assert records[0]["金额"] == "100" and "首页" in records[0]["内容"] and "尾页" in records[0]["内容"]
    connection.close()


def test_engine_build_prompt_shapes():
    prompt = ocr_engine.build_prompt("角色", ["a", "b"], "规则", "示例", "page")
    assert "角色" in prompt and "规则" in prompt and "JSON 数组" in prompt
    assert ocr_engine.build_prompt("角色", ["a"], "", "", "record").find("record") == -1


# ---------- tools ----------

def test_tool_records_view_query():
    from tools.records.view_query import main as tool
    events, emit = _emit_collector()
    result = tool.run({"records": [r for _, r in _rows()],
                       "view_spec": {"group": {"mode": "none"},
                                     "aggregates": [{"column": "页码", "op": "page"}]}},
                      FakeCtx(), emit)
    assert result["rows"][0]["页码"] == 1
    assert events


def test_tool_view_query_bad_spec():
    from tools.records.view_query import main as tool
    with pytest.raises(ToolDomainError):
        tool.run({"records": [], "view_spec": "{bad json"}, FakeCtx(), lambda e: None)


def test_tool_merge_crosspage_join_and_fill():
    from tools.records.merge_crosspage import main as tool
    records = [
        {"项目名称": "甲项目", "送审金额": "100", "页码": 1},
        {"送审金额": "50", "页码": 2},                      # 续行 → join 并入
        {"项目名称": "", "审定金额": "150", "页码": 3},     # fill 继承甲项目
    ]
    out = tool.run({"records": records, "key_field": "项目名称",
                    "modes": ["join"]}, FakeCtx(), lambda e: None)
    # join：一切空键行并入前行（审定金额 150 亦随空键并入）
    assert out["records_count"] == 1
    merged = out["records"][0]
    assert merged["送审金额"] == "100；50" and merged["审定金额"] == "150"

    fill_only = tool.run({"records": records, "key_field": "项目名称",
                          "modes": ["fill"]}, FakeCtx(), lambda e: None)
    assert fill_only["records_count"] == 3
    assert fill_only["records"][2]["项目名称"] == "甲项目"


def test_tool_write_records_roundtrip(tmp_path):
    from tools.ocrdb.write_records import main as tool
    db = str(tmp_path / "w.db")
    out = tool.run({"records": [{"发票号": "X", "页码": 1}], "db": db,
                    "source_path": "x.pdf"}, FakeCtx(), lambda e: None)
    assert out["written"] == 1
    connection = sqlite3.connect(db)
    count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    connection.close()
    assert count == 1


def test_tool_vl_extract_with_fake_client(tmp_path, monkeypatch):
    import tools.img.vl_extract.main as tool_main
    from command_shared import ocr_engine as engine_mod
    pdf = _pdf(tmp_path / "inv.pdf", pages=1)
    db = str(tmp_path / "inv.db")
    monkeypatch.setattr(engine_mod, "call_vl",
                        lambda *a, **k: json.dumps([{"发票号": "F1", "金额": "99"}],
                                                   ensure_ascii=False))
    out = tool_main.run(
        {"file": pdf, "db": db, "fields": ["发票号", "金额"],
         "prompt": "识别发票", "key_name": "dashscope"}, FakeCtx(), lambda e: None)
    assert out["records_count"] == 1 and out["records"][0]["发票号"] == "F1"
    assert out["failed_pages"] == [] and os.path.exists(out["db"])


def test_tool_vl_extract_requires_key(tmp_path, monkeypatch):
    import tools.img.vl_extract.main as tool_main
    pdf = _pdf(tmp_path / "n.pdf", pages=1)
    with pytest.raises(ToolDomainError):
        tool_main.run({"file": pdf}, FakeCtx(keys={}), lambda e: None)

