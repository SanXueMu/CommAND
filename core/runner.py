"""L5 三形态执行器：inproc / subprocess / http 统一契约。

subprocess 契约：stdin 信封 JSON → stdout 结果 JSON；退出码 0=成 / 1=用户错 / 2=系统错 / 3=领域错。
http 契约：POST {entry}/call 信封 → 200 结果 / 422 用户错 / 503 领域错 / 其余系统错。
"""

import importlib.util
import sys
import json
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

import httpx

from core.errors import (
    TaskCancelled,
    ToolDomainError,
    ToolSystemError,
    ToolUserError,
)
from core.protocol import ToolManifest, validate_payload

Emit = Callable[[str, dict], None]


class RunContext:
    """inproc 工具上下文：取消事件由工具在检查点自查；keys 为 CommAND keys 服务的运行时注入。"""

    def __init__(self, handle: str, attempt: int, cancel_event: Any, emit: Emit,
                 keys: dict[str, dict[str, str]] | None = None) -> None:
        self.handle = handle
        self.attempt = attempt
        self.cancel_event = cancel_event
        self.emit = emit
        self.keys: dict[str, dict[str, str]] = keys or {}


class Runner:
    """按 manifest.runtime.kind 分派 adapter；统一超时与 output_schema 终检。"""

    def run(self, manifest: ToolManifest, tool_dir: Path, input: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
        kind = manifest.runtime.kind
        if kind == "inproc":
            result = self._run_inproc(manifest, tool_dir, input, ctx)
        elif kind == "subprocess":
            result = self._run_subprocess(manifest, tool_dir, input, ctx)
        else:
            result = self._run_http(manifest, input)
        validate_payload(manifest.io.output_schema, result, kind="output")
        return result

    @staticmethod
    def _run_inproc(manifest: ToolManifest, tool_dir: Path, input: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
        file_name, _, func_name = manifest.runtime.entry.partition(":")
        module_path = tool_dir / file_name
        if not module_path.exists():
            raise ToolSystemError(f"工具入口不存在: {module_path}")
        # 仓库根入 sys.path：inproc 工具可 import command_shared 共享库
        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        spec = importlib.util.spec_from_file_location(f"command_tool_{manifest.tool.id.replace('.', '_')}", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            func = getattr(module, func_name)
        except AttributeError as exc:
            raise ToolSystemError(f"入口函数缺失: {manifest.runtime.entry}") from exc
        result = func(input, ctx, ctx.emit)
        if not isinstance(result, dict):
            raise ToolSystemError("inproc 工具必须返回 dict")
        return result

    @staticmethod
    def _run_subprocess(manifest: ToolManifest, tool_dir: Path, input: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
        envelope = {"tool": manifest.tool.id, "input": input,
                    "ctx": {"handle": ctx.handle, "attempt": ctx.attempt,
                            **({"keys": ctx.keys} if ctx.keys else {})}}
        proc = subprocess.Popen(
            shlex.split(manifest.runtime.entry),
            cwd=tool_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        writer = threading.Thread(
            target=lambda: (proc.stdin.write(json.dumps(envelope, ensure_ascii=False)), proc.stdin.close()),
            daemon=True,
        )
        writer.start()
        try:
            stdout, stderr = proc.communicate(timeout=manifest.resources.timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise ToolSystemError(f"工具超时（{manifest.resources.timeout_s}s）") from None
        finally:
            writer.join(timeout=1)
        if ctx.cancel_event.is_set():
            raise TaskCancelled(ctx.handle)
        return_code = proc.returncode
        if return_code == 0:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as exc:
                raise ToolSystemError(f"stdout 非合法 JSON: {exc}") from exc
        detail = (stderr or stdout).strip()[:500]
        if return_code == 1:
            raise ToolUserError(detail or "用户错误")
        if return_code == 3:
            raise ToolDomainError(detail or "领域错误")
        raise ToolSystemError(detail or f"系统错误（exit={return_code}）")

    @staticmethod
    def _run_http(manifest: ToolManifest, input: dict[str, Any]) -> dict[str, Any]:
        envelope = {"tool": manifest.tool.id, "input": input}
        try:
            response = httpx.post(
                f"{manifest.runtime.entry.rstrip('/')}/call",
                json=envelope,
                timeout=manifest.resources.timeout_s,
            )
        except httpx.HTTPError as exc:
            raise ToolSystemError(f"http 工具不可达: {exc}") from exc
        if response.status_code == 200:
            return response.json()
        if response.status_code == 422:
            raise ToolUserError(response.text[:500])
        if response.status_code == 503:
            raise ToolDomainError(response.text[:500])
        raise ToolSystemError(f"http {response.status_code}: {response.text[:500]}")
