"""暂停 run 的断点恢复与任务重放。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import resolve_input
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo


class RunRecoveryService:
    """恢复 run 状态并从首个未完成步骤继续派发。"""

    def __init__(self, pipeline_repo: PipelineRepo, run_event_repo: RunEventRepo | None,
                 submit: Callable[[dict[str, Any], str, int, dict[str, Any]], dict[str, Any]],
                 spawn_subrun: Callable[[str, int, dict[str, Any], dict[str, Any], Any,
                                         dict[int, Any]], dict[str, Any]],
                 finish_and_cascade: Callable[[str, str, dict[str, Any] | None], None],
                 resume: Callable[[str], dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._run_events = run_event_repo
        self._submit = submit
        self._spawn_subrun = spawn_subrun
        self._finish_and_cascade = finish_and_cascade
        self._resume = resume

    def resume_run(self, run_id: str) -> dict[str, Any]:
        """恢复即查询（重放）：定位首个未成功步骤分派；已 succeeded 步骤永不重发。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if not self._pipeline_repo.cas_run_status(run_id, ("paused",), "running"):
            if run["status"] == "running":
                return {"run_id": run_id, "status": "running"}
            raise TaskConflictError(f"run 状态不可恢复: {run['status']}")
        self._audit(run_id, "resume_requested")

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        history = self._pipeline_repo.outputs_by_step(run_id)
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        dispatched: dict[str, Any] | None = None
        skipped = self._run_events.skipped_steps(run_id) if self._run_events else set()
        subruns = self._pipeline_repo.get_subruns(run_id)
        for n, step in enumerate(steps):
            if "pipeline" in step:
                sub = subruns.get(n)
                if sub is None:
                    try:
                        self._spawn_subrun(run_id, n, step, run, history.get(n - 1), history)
                        dispatched = {"handle": None}
                    except (ToolUserError, ToolNotFoundError) as exc:
                        self._finish_and_cascade(run_id, "failed", {
                            "kind": "user", "message": f"恢复时第 {n} 步子流无法启动: {exc}"})
                    break
                if sub["status"] == "succeeded":
                    continue
                if sub["status"] == "paused":
                    self._resume(sub["id"])
                    break
                break
            task = latest.get(n)
            if task is None:
                if n in skipped:
                    continue
                try:
                    resolved = resolve_input(step["input"], run["input"],
                                             history.get(n - 1), history)
                    dispatched = self._submit(definition, run_id, n, resolved)
                except (ToolUserError, ToolNotFoundError) as exc:
                    self._pipeline_repo.finish_run(run_id, "failed", error={
                        "kind": "user", "message": f"恢复时第 {n} 步无法入队: {exc}"})
                break
            if task["status"] in ("queued", "running"):
                break
            if task["status"] == "succeeded":
                if n == len(steps) - 1:
                    self._finish_and_cascade(run_id, "succeeded", None)
                continue
            try:
                dispatched = self._submit(definition, run_id, n, dict(task["input"]))
            except ToolNotFoundError as exc:
                self._pipeline_repo.finish_run(run_id, "failed", error={
                    "kind": "user", "message": f"恢复时第 {n} 步工具不可用: {exc}"})
                break
            break

        self._audit(run_id, "resumed", detail={
            "dispatched": dispatched["handle"] if dispatched else None})
        return {"run_id": run_id, "status": "running",
                "dispatched": dispatched["handle"] if dispatched else None}

    def _audit(self, run_id: str, kind: str, task_handle: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
