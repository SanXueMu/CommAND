"""工具域测试：10 个 v2 工具的纯函数链 + 假客户端翻译引擎 + manifest 协议校验。

约定：ctx 用 SimpleNamespace 伪造（handle/keys）；COMMAND_DATA_DIR 指 tmp_path；
LLM 不出网——make_client 被替换为返回 FakeClient（按 prompt 内容应答）。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent

TOOLS = [
    "tools/xlsx/extract_values",
    "tools/pdf/extract_pages",
    "tools/txt/extract_text",
    "tools/ocrdb/extract_units",
    "tools/table/classify_columns",
    "tools/text/dedup_values",
    "tools/text/llm_translate",
    "tools/text/verify_fidelity",
    "tools/xlsx/backfill_dict",
    "tools/docx/render_bilingual",
]


def load_tool(rel: str):
    path = REPO / rel / "main.py"
    spec = importlib.util.spec_from_file_location("tool_" + rel.replace("/", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))
    return SimpleNamespace(
        handle="test-handle",
        keys={"main": {"provider": "dashscope", "base_url": "https://x/v1",
                       "api_key": "sk-test", "is_default": True}},
    )


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = None


class FakeClient:
    """按 prompt 应答：分隔符批翻协议 / JSON 兜底 / 重译修正。"""

    def __init__(self, retranslator=None):
        self.calls: list[dict] = []
        self.retranslator = retranslator

    _SEP_RE = re.compile(r"###(\d+)###\n?(.*?)(?=###\d+###|$)", re.S)

    @staticmethod
    def _segments_from_prompt(prompt: str) -> list[str]:
        found = {int(m.group(1)): m.group(2).strip() for m in FakeClient._SEP_RE.finditer(prompt)}
        return [found[k] for k in sorted(found)]

    def _make(self, responder):
        outer = self

        class Completions:
            def create(self, *, model=None, messages=None, **kw):
                outer.calls.append({"model": model, "messages": messages})
                return _Resp(responder(model, messages[-1]["content"]))

        class Chat:
            completions = Completions()

        return Chat()

    def __post_init__(self):
        raise NotImplementedError


def separator_client(target="中"):
    fake = FakeClient.__new__(FakeClient)
    fake.calls = []
    fake.retranslator = None

    def respond(model, prompt):
        segs = FakeClient._segments_from_prompt(prompt)
        out = "\n".join(f"###{i + 1}###\n{s}{target}" for i, s in enumerate(segs))
        return out or "###1###\nx"

    fake.chat = fake._make(respond)
    return fake


def retranslate_client(bad_first=1):
    """首 n 次给缺数字的坏译文，之后给合格译文（测质检重译环）。"""
    fake = FakeClient.__new__(FakeClient)
    fake.calls = []
    state = {"n": bad_first}
    fake.retranslator = state

    def respond(model, prompt):
        if "The previous translation" in prompt or "Source:" in prompt:
            state["n"] -= 1
            if "###" in prompt:  # 重译仍走批翻分隔符格式
                return "###1###\n净利润 12.5 百万元（重译合格）"
            return "净利润 12.5 百万元（重译合格）"
        segs = FakeClient._segments_from_prompt(prompt)
        parts = []
        for i, s in enumerate(segs):
            parts.append(f"###{i + 1}###\nNet profit million yuan" if state["n"] > 0 else f"###{i + 1}###\nNet profit 12.5 million yuan")
        return "\n".join(parts)

    fake.chat = fake._make(respond)
    return fake


# ---------- manifest 协议校验 ----------


def test_all_manifests_valid():
    import tomllib

    from core.protocol import ToolManifest

    for rel in TOOLS:
        raw = tomllib.loads((REPO / rel / "tool.toml").read_text(encoding="utf-8"))
        assert (REPO / rel / raw["io"]["input_schema"]).exists(), rel
        assert (REPO / rel / raw["io"]["output_schema"]).exists(), rel
        manifest = ToolManifest.from_toml(REPO / rel / "tool.toml")
        assert manifest.io.input_schema and manifest.io.output_schema  # 解析为 dict
        assert manifest.runtime.kind == "inproc"


# ---------- 提取域 ----------


def test_xlsx_extract_classify_dedup_chain(ctx, tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "底稿"
    ws.append(["项目", "Amount", "Date", "说明"])
    ws.append(["营业收入", "100.00", "2023-11-16", "Service fee"])
    ws.append(["营业成本", "80.00", "2023-11-17", "Consulting fee"])
    wb.save(p := tmp_path / "t.xlsx")

    extracted = load_tool("tools/xlsx/extract_values").run({"file": str(p)}, ctx, lambda e: None)
    assert extracted["file_hash"]
    unit = extracted["units"][0]
    assert unit["unit_type"] == "table" and unit["rows"][0][0] == "项目"

    cls = load_tool("tools/table/classify_columns").run(
        {"units": extracted["units"]}, ctx, lambda e: None
    )
    classes = cls["col_classes"][unit["unit_id"]]
    by_col = {c["col"]: c["class"] for c in classes}
    assert by_col[1] == "skip" and by_col[2] == "skip"      # 纯数字列 / 日期列不译
    assert by_col[0] == "enum" and by_col[3] == "enum"      # 低基数文本列（命中字典缓存复用）
    assert cls["segments"] == [
        "项目", "Amount", "Date", "说明",                    # 表头（含字母即收割）
        "营业收入", "Service fee", "营业成本", "Consulting fee",  # 数据：仅非 skip 列
    ]

    dedup = load_tool("tools/text/dedup_values").run({"segments": cls["segments"]}, ctx, lambda e: None)
    assert dedup["unique"] == cls["segments"]
    assert dedup["index_map"] == list(range(8))


def test_dedup_dates_placeholder(ctx):
    mod = load_tool("tools/text/dedup_values")
    out = mod.run(
        {"segments": ["2023-11-16 报告", "2023-11-17 报告", "纯文本"]}, ctx, lambda e: None
    )
    assert out["unique"] == ["[[DATE_1]] 报告", "纯文本"]
    assert out["index_map"] == [0, 0, 1]
    assert out["date_maps"][0] == {"[[DATE_1]]": "2023-11-16"}
    assert out["date_maps"][1] == {"[[DATE_1]]": "2023-11-17"}
    assert out["date_maps"][2] == {}


def test_pdf_and_txt_extract(ctx, tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "审计报告")
    doc.save(pdf := tmp_path / "a.pdf")
    doc.close()

    units = load_tool("tools/pdf/extract_pages").run({"file": str(pdf)}, ctx, lambda e: None)["units"]
    assert units[0]["meta"]["page"] == 1

    (txt := tmp_path / "b.txt").write_text("hello world", encoding="utf-8")
    txt_out = load_tool("tools/txt/extract_text").run({"file": str(txt)}, ctx, lambda e: None)
    assert txt_out["units"][0]["text"] == "hello world"


def test_ocrdb_extract(ctx, tmp_path):
    import json
    import sqlite3

    long_text = "长" * 250
    db = sqlite3.connect(p := tmp_path / "ocr.sqlite")
    db.execute(
        "CREATE TABLE records (id INTEGER PRIMARY KEY, source_path TEXT, page_number INTEGER, data TEXT)"
    )
    db.execute(
        "INSERT INTO records VALUES (1, 'scan.pdf', 1, ?)",
        (json.dumps({"发票号": "INV-1", "金额": "100.00", "备注": long_text}),),
    )
    db.commit()
    db.close()
    units = load_tool("tools/ocrdb/extract_units").run({"file": str(p)}, ctx, lambda e: None)["units"]
    table_units = [u for u in units if u["unit_type"] == "table"]
    text_units = [u for u in units if u["unit_type"] == "text"]
    assert table_units and table_units[0]["rows"][2] == ["发票号 (p1)", "INV-1"]
    assert text_units and text_units[0]["text"] == long_text  # 长值分流


# ---------- 翻译引擎（假客户端） ----------


def test_translate_identity_and_separator(ctx, monkeypatch):
    mod = load_tool("tools/text/llm_translate")
    fake = separator_client()
    monkeypatch.setattr(mod, "make_client", lambda key, base: fake)
    out = mod.run(
        {"segments": ["INV-2024-001", "hello world", "", "fee 100"], "key_name": "main",
         "use_cache": False},
        ctx, lambda e: None,
    )
    assert out["translations"][0] == "INV-2024-001"  # 编号直存
    assert out["translations"][1] == "hello world中"
    assert out["translations"][2] == ""  # 空段直通
    assert out["statuses"] == ["ok", "ok", "ok", "ok"]
    assert out["cache_hits"] == 0


def test_translate_review_and_retranslate(ctx, monkeypatch):
    mod = load_tool("tools/text/llm_translate")
    fake = retranslate_client(bad_first=1)
    monkeypatch.setattr(mod, "make_client", lambda key, base: fake)
    out = mod.run(
        {"segments": ["Net profit was 12.5 million yuan"], "use_cache": False}, ctx, lambda e: None
    )
    assert out["statuses"][0] == "ok"
    assert "12.5" in out["translations"][0]
    assert len(fake.calls) >= 2  # 批翻(坏) → 重译(合格)


def test_translate_requires_key(ctx):
    import copy

    from core.errors import ToolDomainError

    mod = load_tool("tools/text/llm_translate")
    empty = SimpleNamespace(handle="t", keys={})
    with pytest.raises(ToolDomainError):
        mod.run({"segments": ["x"], "use_cache": False}, empty, lambda e: None)


def test_translate_cache_roundtrip(ctx, monkeypatch):
    mod = load_tool("tools/text/llm_translate")
    fake = separator_client()
    monkeypatch.setattr(mod, "make_client", lambda key, base: fake)
    mod.run({"segments": ["hello world"], "use_cache": True}, ctx, lambda e: None)
    n_calls = len(fake.calls)
    out2 = mod.run({"segments": ["hello world"], "use_cache": True}, ctx, lambda e: None)
    assert out2["cache_hits"] == 1 and len(fake.calls) == n_calls  # 二跑零 API


# ---------- 质检 / 回填 / 渲染 ----------


def test_verify_tool(ctx):
    out = load_tool("tools/text/verify_fidelity").run(
        {"sources": ["fee 100", "fee 200"], "translations": ["费用 100", "费用"]},
        ctx, lambda e: None,
    )
    assert out["statuses"] == ["ok", "review"]
    assert "missing_number" in out["reasons"][1]


def _chain_fixtures():
    units = [{"unit_id": "s1", "unit_type": "table",
              "rows": [["项目", "Amount"], ["营业收入", "100.00"], ["管理费用", "20.00"]]}]
    cls = load_tool("tools/table/classify_columns").run({"units": units}, None, lambda e: None)
    dedup = load_tool("tools/text/dedup_values").run({"segments": cls["segments"]}, None, lambda e: None)
    return units, cls, dedup


def test_xlsx_backfill_join(ctx, tmp_path):
    units, cls, dedup = _chain_fixtures()
    n = len(dedup["unique"])
    backfill = load_tool("tools/xlsx/backfill_dict")
    out = backfill.run(
        {"units": units, "col_classes": cls["col_classes"], "ranges": cls["ranges"],
         "segments": cls["segments"], "index_map": dedup["index_map"],
         "date_maps": dedup["date_maps"],
         "translations": [f"译{i}" for i in range(n)],
         "statuses": ["ok"] * (n - 1) + ["review"], "file": "底稿.xlsx"},
        ctx, lambda e: None,
    )
    from openpyxl import load_workbook

    wb = load_workbook(out["path"])
    ws = wb["s1"]
    assert ws.cell(1, 1).value == "译0"   # 表头 项目 → ok
    assert ws.cell(1, 2).value == "译1"   # 表头 Amount → ok
    assert ws.cell(2, 1).value == "译2"   # 营业收入 → ok
    assert ws.cell(3, 1).value.startswith("⚠️")  # review 格保留原文
    assert ws.cell(3, 1).value == "⚠️ 管理费用"
    assert wb.sheetnames[-1] == "对照字典"


def test_docx_render(ctx, tmp_path):
    units = [{"unit_id": "p1", "unit_type": "text", "text": "Audit Summary",
              "meta": {"page": 1, "kind": "text"}}]
    cls = load_tool("tools/table/classify_columns").run({"units": units}, None, lambda e: None)
    dedup = load_tool("tools/text/dedup_values").run({"segments": cls["segments"]}, None, lambda e: None)
    render = load_tool("tools/docx/render_bilingual")
    out = render.run(
        {"units": units, "ranges": cls["ranges"], "index_map": dedup["index_map"],
         "date_maps": dedup["date_maps"], "translations": ["审计总结"],
         "statuses": ["ok"], "file": "报告.pdf"},
        ctx, lambda e: None,
    )
    from docx import Document

    doc = Document(out["path"])
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "审计总结" in text and "第 1 页" in text


def test_docx_render_table_unit(ctx):
    units = [{"unit_id": "t1", "unit_type": "table", "rows": [["项目", "Amount"], ["营业收入", "100.00"]]}]
    cls = load_tool("tools/table/classify_columns").run({"units": units}, None, lambda e: None)
    dedup = load_tool("tools/text/dedup_values").run({"segments": cls["segments"]}, None, lambda e: None)
    n = len(dedup["unique"])
    out = load_tool("tools/docx/render_bilingual").run(
        {"units": units, "ranges": cls["ranges"], "index_map": dedup["index_map"],
         "date_maps": dedup["date_maps"], "col_classes": cls["col_classes"],
         "translations": [f"译{i}" for i in range(n)], "statuses": ["ok"] * n},
        ctx, lambda e: None,
    )
    from docx import Document

    doc = Document(out["path"])
    assert doc.tables and doc.tables[0].cell(1, 0).text == "译2"
