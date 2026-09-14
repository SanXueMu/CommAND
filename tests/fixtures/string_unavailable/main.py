"""能力不可用契约演示：源文件首行为 UNAVAILABLE → 退出码 5（ToolUnavailableError →
任务 failed(kind=unavailable) → run 级 on_failure.fallback_flow 自动降级）。否则逐行反转。

max_attempts = 3 却**不重试**：这正是与 ToolDomainError 的区别（限流可重试，能力不可用重试无意义）。
"""
import json
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)["input"]
        path = Path(payload["file"])
    except (json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"error": f"信封不合法: {exc}"}, ensure_ascii=False))
        sys.exit(1)

    if not path.is_file():
        print(f"文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    marker = payload.get("marker") or "UNAVAILABLE"
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == marker:
        print("模型未开通（Model not found）", file=sys.stderr)
        sys.exit(5)

    print(json.dumps({"segments": [ln[::-1] for ln in lines], "lines": len(lines)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
