"""工作流步骤推进：根据任务终态决定暂停、失败收口或派发下一步。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors import ToolNotFoundError, ToolUserError
from core.pipeline import evaluate_when, resolve_input
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo

FAILURE_STATUSES = {"failed", "failed_review", "cancelled", "interrupted"}


class RunStepCoordinator:
    """只协调单步完成后的推进，不持有具体派发和收口实现。"""

    def __init__(self, pipeline_repo: PipelineRepo,
                 run_event_repo: RunEventRepo | None,
                 submit: Callable[[dict[str, Any], str, int, dict[str, Any]], dict[str, Any]],
                 spawn_subrun: Callable[[str, int, dict[str, Any], dict[str, Any], Any,
                                         dict[int, Any]], dict[str, Any]],
                 finish_and_cascade: Callable[[str, str, dict[str, Any] | None], None]) -> None:
        self._pipeline_repo = pipeline_repo
        self._run_events = run_event_repo
        self._submit = submit
        self._spawn_subrun = spawn_subrun
        self._finish_and_cascade = finish_and_cascade

    def advance(self, task: dict[str, Any]) -> None:
        """任务终态钩子：成功推进下步，失败收口，重复调用无副作用。"""
        run_id = task.get("pipeline_run")
        if not run_id:
            return
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            return
        if run["status"] == "paused":
            if task["status"] == "succeeded":
                self._pipeline_repo.set_run_progress(run_id, task["step_index"] + 1)
                self._audit(run_id, task["handle"], "paused_at_boundary",
                            {"next_index": task["step_index"] + 1})
            return
        if run["status"] != "running":
            return
        if task["status"] == "paused":
            self._audit(run_id, task["handle"], "step_paused",
                        {"step_index": task["step_index"], "error": task.get("error")})
            self._pipeline_repo.cas_run_status(run_id, ("running",), "paused")
            return
        if task["status"] in FAILURE_STATUSES:
            self._audit(run_id, task["handle"], "step_failed",
                        {"step_index": task["step_index"], "status": task["status"]})
            self._finish_and_cascade(run_id, task["status"], task.get("error"))
            return
        if task["status"] != "succeeded":
            return
        self._audit(run_id, task["handle"], "step_completed",
                    {"step_index": task["step_index"]})

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        history = self._pipeline_repo.outputs_by_step(run_id)
        next_index = task["step_index"] + 1
        prev_output = task["output"]
        while next_index < len(steps):
            step = steps[next_index]
            if "when" in step and not evaluate_when(
                    step["when"], run["input"], prev_output, history):
                self._audit(run_id, None, "step_skipped",
                            {"step_index": next_index, "when": step["when"]})
                next_index += 1
                continue
            break
        if next_index >= len(steps):
            self._finish_and_cascade(run_id, "succeeded", None)
            return

        step = steps[next_index]
        if "pipeline" in step:
            try:
                self._spawn_subrun(run_id, next_index, step, run, prev_output, history)
            except ToolUserError:
                pass
            return
        try:
            resolved = resolve_input(step["input"], run["input"], prev_output, history)
            self._submit(definition, run_id, next_index, resolved)
        except ToolUserError as exc:
            self._finish_and_cascade(run_id, "failed", {
                "kind": "user", "message": f"第 {next_index} 步无法入队: {exc}"})
        except ToolNotFoundError as exc:
            self._finish_and_cascade(run_id, "failed", {
                "kind": "user", "message": f"第 {next_index} 步工具不可用: {exc}"})

    def _audit(self, run_id: str, task_handle: str | None, kind: str,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
