"""Translee v2 全自动流冒烟：上传→跑管线→轮询→断言产物。

用法：uv run python scripts/smoke_translee_flow.py [--api http://127.0.0.1:8000] \
        [--flow flow.translate.xlsx] [--file 样例.xlsx] [--key mock]
前置：server 已起、register_translee_flows.py 已执行、LLM key 已注册（名称=key 参数）。
"""
from __future__ import annotations

import argparse
import json
import sys
import subprocess
import time
import urllib.request
from pathlib import Path


def upload(api: str, file: Path) -> str:
    out = subprocess.run(
        ["curl", "-sS", "-X", "POST", f"{api}/api/files", "-F", f"file=@{file}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)["path"]


def call(api: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{api}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--flow", default="flow.translate.xlsx")
    ap.add_argument("--file", required=True)
    ap.add_argument("--key", default="mock")
    ap.add_argument("--mock-base", default="http://127.0.0.1:8765/v1")
    ap.add_argument("--no-mock-key", action="store_true",
                    help="跳过 mock 密钥注册（真实 key 已就绪时使用）")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    path = upload(args.api, Path(args.file))
    print(f"已上传: {path}")
    # mock key 幂等注册（真实环境用真实 key_name 跳过此段：--key 传真实名 + --no-mock-key）
    if not args.no_mock_key:
        call(args.api, "PUT", f"/api/keys/{args.key}",
             {"name": args.key, "provider": "openai", "base_url": args.mock_base,
              "api_key": "sk-mock", "is_default": False})
        print(f"mock 密钥就绪: {args.key} → {args.mock_base}")
    run = call(args.api, "POST", f"/api/pipelines/{args.flow}/run",
               {"input": {"file": path, "key_name": args.key,
                          "target_lang": "中文", "model": ""}})
    run_id = run["run_id"]
    print(f"管线运行: {run_id}")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        detail = call(args.api, "GET", f"/api/pipeline-runs/{run_id}")
        status = detail["run"]["status"]
        if status in ("succeeded", "failed", "failed_review", "cancelled"):
            err = detail["run"].get("error")
            print(f"状态: {status}" + (f"  错误: {err}" if err else ""))
            for t in detail.get("tasks", []):
                out = t.get("output") or {}
                line = f"step{t.get('step_index')} {t['tool_id']} {t['status']}"
                if out.get("path"):
                    line += f" → {out['path']}"
                if t.get("error"):
                    line += f"  错误: {t['error'].get('message', '')[:200]}"
                print(line)
            return 0 if status == "succeeded" else 1
        time.sleep(1)
    print("超时未收口")
    return 2


if __name__ == "__main__":
    sys.exit(main())
