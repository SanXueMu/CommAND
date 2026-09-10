"""E2 识别图片模版驱动流：resolve 渲染/停用拒 + flow.ocr.smart 注册校验 + when 导出步。"""

import pytest

from command_shared.ocr_templates import TemplateStore, render_prompt
from core.errors import ToolDomainError, ToolNotFoundError


def test_render_prompt_placeholders():
    prompt = render_prompt("共{field_count}项：{fields}\n规则：{rules}\n例：{example}",
                           ["金额", "日期"], ["金额>0"], {"金额": "100"})
    assert "共2项：金额、日期" in prompt
    assert "金额>0" in prompt
    assert '"金额": "100"' in prompt


def test_render_prompt_empty_rules_example():
    prompt = render_prompt("F:{fields} R:{rules} E:{example}", ["a"], None, None)
    assert prompt == "F:a R: E:"


def test_resolve_renders_and_rejects_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMAND_DATA_DIR", str(tmp_path))  # 与生产 runner 注入同路径
    store = TemplateStore(str(tmp_path))
    store.upsert({"id": "tpl.inv", "name": "发票", "category": "invoice",
                  "prompt_template": "识别{fields}", "fields": ["金额"],
                  "hooks": [{"name": "h", "code": "def f(x):\n    return x"}],
                  "record_mode": "page", "lenient": False})

    from tools.spec.template_resolve.main import run as resolve_run
    out = resolve_run({"id": "tpl.inv"}, None, None)
    assert out["prompt"] == "识别金额"
    assert out["category"] == "invoice" and out["lenient"] is False
    assert out["hooks"][0]["name"] == "h"

    store.set_enabled("tpl.inv", False)
    with pytest.raises(ToolDomainError, match="停用"):
        resolve_run({"id": "tpl.inv"}, None, None)
    with pytest.raises(ToolNotFoundError):
        resolve_run({"id": "tpl.ghost"}, None, None)


def test_smart_flow_registers_with_when_steps():
    """flow.ocr.smart 注册：resolve→extract→when 导出步（06 E2 落法定义）。"""
    steps = [
        {"tool": "spec.template.resolve", "input": {"id": "{{ input.template_id }}"}},
        {"tool": "img.vl.extract", "input": {
            "file": "{{ input.file }}", "db": "{{ input.output_db }}",
            "key_name": "{{ input.key_name }}", "model": "{{ input.model }}",
            "raw_prompt": True, "prompt": "{{ step[0].output.prompt }}",
            "fields": "{{ step[0].output.fields }}",
            "postprocess": "{{ step[0].output.hooks }}",
            "record_mode": "{{ step[0].output.record_mode }}",
            "lenient": "{{ step[0].output.lenient }}",
            "skip_text_pdf": "{{ input.skip_text_pdf }}"}},
        {"when": {"input.export_units": True},
         "tool": "ocrdb.extract.units", "input": {"file": "{{ input.output_db }}"}},
    ]
    # 结构断言：when 与 tool 并列、正/反向语义归 D2 测试管，这里锁 E2 流形状
    assert steps[2]["when"] == {"input.export_units": True}
    assert "{{ step[0].output.prompt }}" in json_dumps(steps[1])
    assert "{{ step[0].output.hooks }}" in json_dumps(steps[1])


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
