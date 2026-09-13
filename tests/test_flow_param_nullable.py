"""流参数可空性回归：被流步骤 `{{ input.X }}` 引用、且工作台允许留空的参数，
其工具 input.schema 必须接受 null——否则入队校验报 `$.X is not of type 'string'`。

背景：工作台留空字段会发 null；模板引擎要求「模板引用必在、值可为 null」。
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# (工具目录, 必须可空的参数名)
CASES = [
    ("tools/text/llm_translate", ["key_name", "model", "fallback_model", "target_lang", "source_lang", "terms"]),
    ("tools/pdf/ocr_addlayer", ["languages", "force"]),
    ("tools/pdf/render_translated", ["mode"]),
]


@pytest.mark.parametrize("tool,keys", CASES)
def test_template_referenced_params_are_nullable(tool, keys):
    schema = json.loads((ROOT / tool / "input.schema.json").read_text(encoding="utf-8"))
    for key in keys:
        prop = schema["properties"][key]
        types = prop["type"]
        types = types if isinstance(types, list) else [types]
        assert "null" in types, f"{tool}.{key} 必须可空（工作台留空会传 null）"


def test_llm_translate_null_payload_validates():
    import jsonschema

    schema = json.loads(
        (ROOT / "tools/text/llm_translate/input.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(
        {"segments": ["x"], "key_name": "k", "model": None, "source_lang": None,
         "target_lang": None, "terms": None},
        schema,
    )
