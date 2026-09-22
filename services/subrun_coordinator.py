"""子运行协调：创建子 run 并派发其首步。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.errors import ToolUserError
from core.pipeline import resolve_input
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo


class SubrunCoordinator:
    """负责 workflow 的 pipeline 步骤实例化，不负责父级收口。"""

    def __init__(self, pipeline_repo: PipelineRepo, run_event_repo: RunEventRepo | None,
                 submit: Callable[[dict[str, Any], str, int, dict[str, Any]], dict[str, Any]]) -> None:
        self._pipeline_repo = pipeline_repo
        self._run_events = run_event_repo
        self._submit = submit

    def spawn(self, parent_run_id: str, step_index: int, step: dict[str, Any],
              run: dict[str, Any], prev_output: Any,
              history: dict[int, Any]) -> dict[str, Any]:
        """创建子 run，并派发子流首步。"""
        flow_id = step["pipeline"]
        sub_definition = self._pipeline_repo.get_definition(flow_id)
        if sub_definition is None or sub_definition.get("type") != "flow":
            self._pipeline_repo.finish_run_forced(parent_run_id, "failed", error={
                "kind": "user", "message": f"第 {step_index} 步引用的流不可用: {flow_id}"})
            raise ToolUserError(f"第 {step_index} 步引用的流不可用: {flow_id}")
        try:
            resolved = resolve_input(step["input"], run["input"], prev_output, history)
        except ToolUserError as exc:
            self._pipeline_repo.finish_run_forced(parent_run_id, "failed", error={
                "kind": "user", "message": f"第 {step_index} 步流输入解析失败: {exc}"})
            raise
        sub_run_id = self._pipeline_repo.create_run(
            flow_id, resolved, parent_run_id=parent_run_id, parent_step_index=step_index)
        self._audit(parent_run_id, "subrun_created", detail={
            "step_index": step_index, "subrun_id": sub_run_id, "pipeline_id": flow_id})
        sub_first = sub_definition["steps"][0]
        sub_resolved = resolve_input(sub_first["input"], resolved, None, {})
        submitted = self._submit(sub_definition, sub_run_id, 0, sub_resolved)
        return {"subrun_id": sub_run_id, "handle": submitted["handle"]}

    def _audit(self, run_id: str, kind: str, task_handle: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
