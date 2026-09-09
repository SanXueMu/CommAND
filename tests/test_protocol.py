"""protocol 模块测试：manifest 解析/校验与信封模型。"""

from pathlib import Path

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
