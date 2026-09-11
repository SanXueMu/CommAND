"""subprocess 契约参考实现：stdin 信封 JSON → stdout 结果 JSON；退出码 0/1/2/3。"""
import json
import sys


def main() -> None:
    try:
        envelope = json.load(sys.stdin)
        segments = envelope["input"]["segments"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"error": f"信封不合法: {exc}"}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(
        {"segments": [s[::-1] for s in segments]},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
