"""暂停契约演示：源文件首行为 PAUSE（或 input.marker）→ 退出码 4（ToolPauseError → 任务 paused）；
否则返回逐行反转结果。与真实场景同构：**输入路径不变、修好文件后 resume 即续跑**。
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

    marker = payload.get("marker") or "PAUSE"
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == marker:
        print("需要人工介入：请修正源文件后点「继续」", file=sys.stderr)
        sys.exit(4)

    print(json.dumps({"segments": [ln[::-1] for ln in lines], "lines": len(lines)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
