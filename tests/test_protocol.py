"""protocol 模块测试：manifest 解析/校验与信封模型。"""

from pathlib import Path
import json

import pytest
from pydantic import ValidationError

from core.protocol import Envelope, ToolManifest


def test_manifest_from_toml_with_schema_file_refs(sample_manifest_toml: Path):
    manifest = ToolManifest.from_toml(sample_manifest_toml)
    assert manifest.tool.id == "text.llm.translate"
    assert manifest.io.input_schema["type"] == "object"
    assert manifest.runtime.kind == "inproc"
    assert manifest.resources.max_attempts == 3


def test_manifest_rejects_non_dotted_id(tmp_path: Path):
    path = tmp_path / "tool.toml"
    path.write_text(
        """
[tool]
id = "translate"
name = "x"
version = "1.0.0"

[io]
input_schema = {type = "object"}
output_schema = {type = "object"}
input_types = ["text.raw"]
output_types = ["text.ok"]

[runtime]
kind = "inproc"
entry = "main.py:run"

[resources]
timeout_s = 60
concurrency = 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        ToolManifest.from_toml(path)


def test_manifest_rejects_schema_without_type(tmp_path: Path):
    path = tmp_path / "tool.toml"
    path.write_text(
        """
[tool]
id = "text.llm.translate"
name = "x"
version = "1.0.0"

[io]
input_schema = {properties = {}}
output_schema = {type = "object"}
input_types = ["text.raw"]
output_types = ["text.ok"]

[runtime]
kind = "inproc"
entry = "main.py:run"

[resources]
timeout_s = 60
concurrency = 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        ToolManifest.from_toml(path)


def test_envelope_is_self_contained():
    env = Envelope(tool="text.llm.translate", input={"segments": ["a"]})
    assert env.tool == "text.llm.translate"
    assert env.input == {"segments": ["a"]}


def test_manifest_accepts_and_passes_ui_section(tmp_path: Path):
    """[ui] 呈现声明：宽松透传，骨架不解释（CommWEB ToolFace 消费）。"""
    toml = tmp_path / "tool.toml"
    toml.write_text(
        """
[tool]
id = "demo.ui.tool"
name = "演示"
version = "1.0.0"

[io]
input_schema = "input.schema.json"
output_schema = "output.schema.json"
input_types = []
output_types = []

[runtime]
kind = "inproc"
entry = "main"

[resources]
timeout_s = 60
concurrency = 1

[ui]
order = ["mode"]

[ui.field.mode]
widget = "radio"
label = "粒度"
""", encoding="utf-8")
    json.dump({"type": "object", "properties": {}}, open(tmp_path / "input.schema.json", "w"), ensure_ascii=False)
    json.dump({"type": "object", "properties": {}}, open(tmp_path / "output.schema.json", "w"), ensure_ascii=False)

    manifest = ToolManifest.from_toml(toml)
    assert manifest.ui["order"] == ["mode"]
    assert manifest.ui["field"]["mode"]["widget"] == "radio"


def test_status_catalog_integrity():
    """状态目录：值唯一、组别合法、terminal 与组语义一致（成功/失败/取消皆终态）。"""
    from core.status import STATUS_CATALOG

    values = [s["value"] for s in STATUS_CATALOG]
    assert len(values) == len(set(values))
    valid_groups = {"active", "succeeded", "failed", "cancelled"}
    for status in STATUS_CATALOG:
        assert status["group"] in valid_groups
        if status["group"] == "active":
            assert status["terminal"] is False
        else:
            assert status["terminal"] is True
