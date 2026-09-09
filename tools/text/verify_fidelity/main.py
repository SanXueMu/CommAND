"""译文保真质检（translee verify 独立化）：逐对校验，输出状态与原因。

translate 工具内部已含同一质检（重译环）；本工具用于管线终检审计与独立 QA 场景。
"""
from __future__ import annotations

from command_shared.verify import verify_pair


def run(input: dict, ctx, emit) -> dict:
    sources: list[str] = input["sources"]
    translations: list[str] = input["translations"]
    if len(sources) != len(translations):
        from core.errors import ToolDomainError

        raise ToolDomainError(f"sources/translations 长度不一致: {len(sources)} vs {len(translations)}")

    statuses: list[str] = []
    reasons: list[str] = []
    for src, dst in zip(sources, translations):
        ok, reason = verify_pair(src, dst)
        statuses.append("ok" if ok else "review")
        reasons.append(reason)

    ok_count = sum(1 for s in statuses if s == "ok")
    emit({"phase": "verified", "total": len(sources), "ok": ok_count})
    return {"statuses": statuses, "reasons": reasons, "ok_count": ok_count, "total": len(sources)}
