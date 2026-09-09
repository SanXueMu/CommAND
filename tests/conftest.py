"""集中 fixture：manifest 样本工厂与临时目录隔离。"""

from pathlib import Path

import pytest

VALID_MANIFEST_TOML = """
[tool]
id = "text.llm.translate"
name = "纯翻译"
version = "1.0.0"
description = "批量翻译"

[io]
input_schema = "input.schema.json"
output_schema = "output.schema.json"
input_types = ["text.complete[]"]
output_types = ["text.translated[]"]

[runtime]
kind = "inproc"
entry = "main.py:run"

[resources]
timeout_s = 3600
concurrency = 2
max_attempts = 3
"""


@pytest.fixture
def sample_manifest_toml(tmp_path: Path) -> Path:
    tool_dir = tmp_path / "text" / "llm_translate"
    tool_dir.mkdir(parents=True)
    (tool_dir / "input.schema.json").write_text(
        '{"type": "object", "properties": {"segments": {"type": "array"}}}',
        encoding="utf-8",
    )
    (tool_dir / "output.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    (tool_dir / "tool.toml").write_text(VALID_MANIFEST_TOML, encoding="utf-8")
    return tool_dir / "tool.toml"
