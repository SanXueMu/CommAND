"""父子 run 完成后的级联收口。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo


class SubrunCascadeCoordinator:
    """把子 run 结果转换为父流程步骤结果，或向父级传播失败。"""

    def __init__(self, pipeline_repo: PipelineRepo, run_event_repo: RunEventRepo | None,
                 finish_and_cascade: Callable[[str, str, dict[str, Any] | None], None],
                 advance: Callable[[dict[str, Any]], None]) -> None:
        self._pipeline_repo = pipeline_repo
        self._run_events = run_event_repo
        self._finish_and_cascade = finish_and_cascade
        self._advance = advance

    def cascade(self, run_id: str, status: str,
                error: dict[str, Any] | None = None) -> None:
        run = self._pipeline_repo.get_run(run_id)
        if run is None or run["parent_run_id"] is None:
            return
        parent_run_id, step_index = run["parent_run_id"], run["parent_step_index"]
        self._audit(parent_run_id, "subrun_finished", detail={
            "step_index": step_index, "subrun_id": run_id, "status": status})
        if status != "succeeded":
            self._finish_and_cascade(parent_run_id, status, error or {
                "kind": "system", "message": f"子流失败（步 {step_index}）"})
            return
        outputs = self._pipeline_repo.outputs_by_step(run_id)
        last_output = outputs[max(outputs)] if outputs else None
        self._advance({
            "pipeline_run": parent_run_id, "step_index": step_index,
            "status": "succeeded", "output": last_output, "error": None,
            "handle": None, "attempt": 1, "input": run["input"]})

    def _audit(self, run_id: str, kind: str, task_handle: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
