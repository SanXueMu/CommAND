"""runner 单元测试：三形态契约（inproc / subprocess / http mock）。"""

import threading
from pathlib import Path

import httpx
import pytest

from core.errors import TaskCancelled, ToolDomainError, ToolSystemError, ToolUserError
from core.protocol import IoSection, ResourcesSection, RuntimeSection, ToolManifest, ToolSection
from core.runner import RunContext, Runner


def make_manifest(kind: str, entry: str) -> ToolManifest:
    return ToolManifest(
        tool=ToolSection(id="test.dev.echo", name="回声", version="1.0.0"),
        io=IoSection(
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "required": ["segments"],
                "properties": {"segments": {"type": "array"}},
            },
            input_types=["text.raw"],
            output_types=["text.raw"],
        ),
        runtime=RuntimeSection(kind=kind, entry=entry),
        resources=ResourcesSection(timeout_s=5, concurrency=1),
    )


def make_ctx(cancel_event=None) -> RunContext:
    return RunContext(
        handle="t_test",
        attempt=1,
        cancel_event=cancel_event or threading.Event(),
        emit=lambda type, data: None,
    )


ECHO_TOOL = '''
def run(input, ctx, emit):
    emit("progress", {"done": 1, "total": 1})
    return {"segments": input["segments"]}
'''


def write_tool(tmp_path: Path, code: str) -> Path:
    (tmp_path / "main.py").write_text(code, encoding="utf-8")
    return tmp_path


def test_inproc_happy_path_and_output_validation(tmp_path: Path):
    tool_dir = write_tool(tmp_path, ECHO_TOOL)
    manifest = make_manifest("inproc", "main.py:run")
    result = Runner().run(manifest, tool_dir, {"segments": ["a"]}, make_ctx())
    assert result == {"segments": ["a"]}


def test_inproc_output_schema_violation(tmp_path: Path):
    bad_tool = "def run(input, ctx, emit):\n    return {'wrong': 1}\n"
    tool_dir = write_tool(tmp_path, bad_tool)
    manifest = make_manifest("inproc", "main.py:run")
    with pytest.raises(ToolUserError):
        Runner().run(manifest, tool_dir, {"segments": ["a"]}, make_ctx())


def test_inproc_cancel_checkpoint(tmp_path: Path):
    cancel_tool = (
        "def run(input, ctx, emit):\n"
        "    from core.errors import TaskCancelled\n"
        "    if ctx.cancel_event.is_set():\n"
        "        raise TaskCancelled(ctx.handle)\n"
        "    return {'segments': []}\n"
    )
    tool_dir = write_tool(tmp_path, cancel_tool)
    manifest = make_manifest("inproc", "main.py:run")
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(TaskCancelled):
        Runner().run(manifest, tool_dir, {}, make_ctx(cancelled))


SUBPROC_TOOL = '''
import json, sys
envelope = json.load(sys.stdin)
code = envelope["input"].get("exit", 0)
if code == 0:
    print(json.dumps({"segments": ["ok"]}))
else:
    print("boom", file=sys.stderr)
    sys.exit(code)
'''


@pytest.mark.parametrize("exit_code,exc", [
    (0, None),
    (1, ToolUserError),
    (3, ToolDomainError),
    (2, ToolSystemError),
])
def test_subprocess_exit_code_contract(tmp_path: Path, exit_code: int, exc):
    tool_dir = write_tool(tmp_path, SUBPROC_TOOL)
    manifest = make_manifest("subprocess", "python3 main.py")
    if exit_code == 0:
        result = Runner().run(manifest, tool_dir, {"exit": 0}, make_ctx())
        assert result == {"segments": ["ok"]}
    else:
        with pytest.raises(exc):
            Runner().run(manifest, tool_dir, {"exit": exit_code}, make_ctx())


def test_http_status_contract(monkeypatch: pytest.MonkeyPatch):
    manifest = make_manifest("http", "http://fake.local:9999")

    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"segments": ["ok"]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Runner().run(manifest, Path("."), {}, make_ctx()) == {"segments": ["ok"]}


def test_http_422_is_user_error(monkeypatch: pytest.MonkeyPatch):
    manifest = make_manifest("http", "http://fake.local:9999")

    def fake_post(url, json=None, timeout=None):
        return httpx.Response(422, text="input 不合法", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ToolUserError):
        Runner().run(manifest, Path("."), {}, make_ctx())
