"""运行终态收口、能力不可用处理与 fallback。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from store.pipeline_repo import PipelineRepo

logger = logging.getLogger("command.pipeline")

UNAVAILABLE_HINT = (
    "该密钥/模型当前不可用（未开通、无权限或额度问题）：请在「APIKey管理」确认密钥已开通该模型，"
    "换好密钥后点「继续」重试；若该密钥确实没有该模型权限，请改用其它处理方式"
    "（例如把图片转为 PDF 后用「版式翻译」）"
)


class RunCompletionService:
    def __init__(self, pipeline_repo: PipelineRepo, audit: Callable[..., None],
                 purge_decisive: Callable[..., None], run: Callable[..., dict[str, Any]],
                 cascade: Callable[..., None]) -> None:
        self._pipeline_repo = pipeline_repo
        self._audit = audit
        self._purge_decisive = purge_decisive
        self._run = run
        self._cascade = cascade

    def fallback_flow_for(self, run: dict[str, Any] | None, status: str,
                          error: dict[str, Any] | None) -> str | None:
        if run is None or status != "failed" or not error:
            return None
        if str(error.get("kind") or "") != "unavailable":
            return None
        if run.get("parent_run_id") or run.get("fallback_of"):
            return None
        definition = self._pipeline_repo.get_definition(str(run.get("pipeline_id"))) or {}
        flow = (definition.get("on_failure") or {}).get("fallback_flow")
        return flow if isinstance(flow, str) and flow else None

    def should_pause_instead(self, run: dict[str, Any] | None, status: str,
                             error: dict[str, Any] | None) -> bool:
        if run is None or status != "failed" or not error:
            return False
        if str(error.get("kind") or "") != "unavailable":
            return False
        return run.get("parent_run_id") is None and not run.get("fallback_of")

    def finish_and_cascade(self, run_id: str, status: str,
                           error: dict[str, Any] | None = None) -> None:
        run = self._pipeline_repo.get_run(run_id)
        fallback_flow = self.fallback_flow_for(run, status, error)
        if fallback_flow:
            error = dict(error or {})
            error["message"] = (f"{error.get('message', '')}"
                                 f"（能力不可用，已自动改用「{fallback_flow}」重跑）")
            error["fallback_flow"] = fallback_flow
        if not fallback_flow and self.should_pause_instead(run, status, error):
            error = dict(error or {})
            error["message"] = f"{error.get('message', '')}（能力不可用，已暂停：{UNAVAILABLE_HINT}）"
            error["hint"] = UNAVAILABLE_HINT
            error["paused_unavailable"] = True
            self._pipeline_repo.finish_run(run_id, "paused", error=error)
            return
        self._pipeline_repo.finish_run(run_id, status, error=error)
        self._purge_decisive(run_id, status, error, fallback_flow is not None)
        if fallback_flow and run is not None:
            try:
                fb_input = dict(run.get("input") or {})
                fb_def = self._pipeline_repo.get_definition(fallback_flow) or {}
                if "reason" in ((fb_def.get("input_schema") or {}).get("properties") or {}):
                    fb_input["reason"] = (
                        f"上游「{run.get('pipeline_id')}」能力不可用（{(error or {}).get('message', '')}），"
                        "已自动降级为不翻译留档；如需翻译请修复密钥/模型后重跑")
                created = self._run(fallback_flow, fb_input, batch_id=run.get("batch_id"),
                                   fallback_of=run_id)
                self._audit(run_id, None, "run_fallback",
                            detail={"to_run": created["run_id"], "fallback_flow": fallback_flow})
                self._audit(created["run_id"], None, "run_fallback",
                            detail={"from_run": run_id, "fallback_flow": fallback_flow})
            except Exception:  # noqa: BLE001
                logger.exception("失败降级启动失败 run=%s fallback=%s", run_id, fallback_flow)
        self._cascade(run_id, status, error)
