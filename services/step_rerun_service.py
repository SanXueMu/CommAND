"""单步骤断点重跑。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import resolve_input
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo


class StepRerunService:
    """以留档 input 为基础重派发单个步骤。"""

    def __init__(self, pipeline_repo: PipelineRepo, run_event_repo: RunEventRepo | None,
                 cancel: Callable[[str], None],
                 submit: Callable[[dict[str, Any], str, int, dict[str, Any]], dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._run_events = run_event_repo
        self._cancel = cancel
        self._submit = submit

    def rerun_step(self, run_id: str, step_index: int,
                   override: dict[str, Any] | None = None) -> dict[str, Any]:
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if run["status"] == "running":
            raise TaskConflictError("run 运行中，先暂停再重跑")
        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        if not 0 <= step_index < len(steps):
            raise ToolUserError(f"步骤号越界: {step_index}（共 {len(steps)} 步）")

        latest = self._pipeline_repo.latest_task_by_step(run_id)
        task = latest.get(step_index)
        if task is not None and task["status"] in ("queued", "running"):
            raise TaskConflictError(f"第 {step_index} 步仍在执行，先中止再重跑")
        if not self._pipeline_repo.cas_run_status(
                run_id, ("paused", "succeeded", "failed", "failed_review",
                         "cancelled", "interrupted"), "running"):
            raise TaskConflictError(f"run 状态不可重跑: {run['status']}")
        self._audit(run_id, "rerun_requested",
                    detail={"step_index": step_index, "override": override or {}})
        if override:
            self._audit(run_id, "override_applied", task_handle=task["handle"] if task else None,
                        detail={"step_index": step_index, "fields": sorted(override)})

        for later in (h for i, t in latest.items() if i > step_index
                      for h in [t["handle"]] if t["status"] in ("queued", "running")):
            try:
                self._cancel(later)
            except Exception:  # noqa: BLE001
                pass

        if task is not None:
            resolved = dict(task["input"] or {})
            resolved.update(override or {})
        else:
            history = self._pipeline_repo.outputs_by_step(run_id)
            resolved = resolve_input(steps[step_index]["input"], run["input"],
                                     history.get(step_index - 1), history)
            resolved.update(override or {})
        try:
            submitted = self._submit(definition, run_id, step_index, resolved)
        except ToolNotFoundError as exc:
            self._pipeline_repo.finish_run(run_id, "failed", error={
                "kind": "user", "message": f"重跑第 {step_index} 步工具不可用: {exc}"})
            raise
        self._audit(run_id, "step_rerun", task_handle=submitted["handle"],
                    detail={"step_index": step_index, "attempt": submitted.get("attempt", 1)})
        return {"run_id": run_id, "step_index": step_index,
                "handle": submitted["handle"], "status": "running"}

    def _audit(self, run_id: str, kind: str, task_handle: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
