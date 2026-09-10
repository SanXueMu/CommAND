"""L4 管线编排：定义注册 / 运行提交 / 终态推进（由 scheduler 钩子驱动）。"""

from __future__ import annotations

import re
from typing import Any

from core.errors import TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import resolve_input
from services.dispatch_service import DispatchService
from store.db import Db
from store.pipeline_repo import PipelineRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

PIPELINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

FAILURE_STATUSES = {"failed", "failed_review", "cancelled", "interrupted"}


class PipelineService:
    """线性管线：首步提交 → 每步 succeeded 后解析模板入队下步 → 终态收口。"""

    def __init__(
        self,
        db: Db,
        pipeline_repo: PipelineRepo,
        task_repo: TaskRepo,
        tool_repo: ToolRepo,
        dispatch_service: DispatchService,
    ) -> None:
        self._db = db
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._dispatch = dispatch_service

    def register(self, pipeline_id: str, name: str, steps: list[dict[str, Any]], doc_md: str | None = None) -> dict[str, Any]:
        if not PIPELINE_ID_PATTERN.match(pipeline_id):
            raise ToolUserError(f"管线 id 须为点分多段（小写）: {pipeline_id}")
        if not steps or not isinstance(steps, list):
            raise ToolUserError("steps 须为非空数组")
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "tool" not in step or "input" not in step:
                raise ToolUserError(f"第 {i} 步须含 tool 与 input")
            if self._tool_repo.get(step["tool"]) is None:
                raise ToolNotFoundError(f"第 {i} 步工具未注册: {step['tool']}")
            if not isinstance(step["input"], dict):
                raise ToolUserError(f"第 {i} 步 input 须为对象")
        self._pipeline_repo.upsert_definition(pipeline_id, name, steps, doc_md=doc_md)
        return {"id": pipeline_id, "name": name, "steps": steps, "status": "registered"}

    def list(self) -> list[dict[str, Any]]:
        return self._pipeline_repo.list_definitions()

    def get(self, pipeline_id: str) -> dict[str, Any]:
        definition = self._pipeline_repo.get_definition(pipeline_id)
        if definition is None:
            raise TaskNotFoundError(f"管线不存在: {pipeline_id}")
        return definition

    def run(self, pipeline_id: str, input: dict[str, Any]) -> dict[str, Any]:
        definition = self.get(pipeline_id)
        run_id = self._pipeline_repo.create_run(pipeline_id, input)
        first = definition["steps"][0]
        try:
            resolved = resolve_input(first["input"], input, None, {})
            submitted = self._dispatch.submit(
                first["tool"], resolved, pipeline_run=run_id, step_index=0)
        except ToolUserError as exc:
            self._pipeline_repo.finish_run(run_id, "failed", error={
                "kind": "user", "message": str(exc)})
            raise
        return {
            "run_id": run_id,
            "status": "running",
            "pipeline_id": pipeline_id,
            "first_handle": submitted["handle"],
        }

    def advance(self, task: dict[str, Any]) -> None:
        """scheduler 终态钩子：succeeded → 推进下步；失败终态 → run 收口。幂等。"""
        run_id = task.get("pipeline_run")
        if not run_id:
            return
        run = self._pipeline_repo.get_run(run_id)
        if run is None or run["status"] != "running":
            return
        if task["status"] in FAILURE_STATUSES:
            self._pipeline_repo.finish_run(run_id, task["status"], error=task.get("error"))
            return
        if task["status"] != "succeeded":
            return

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        next_index = task["step_index"] + 1
        if next_index >= len(steps):
            self._pipeline_repo.finish_run(run_id, "succeeded")
            return

        step = steps[next_index]
        history = self._pipeline_repo.outputs_by_step(run_id)
        try:
            resolved = resolve_input(step["input"], run["input"], task["output"], history)
            self._dispatch.submit(step["tool"], resolved,
                                  pipeline_run=run_id, step_index=next_index)
        except ToolUserError as exc:
            self._pipeline_repo.finish_run(run_id, "failed", error={
                "kind": "user",
                "message": f"第 {next_index} 步无法入队: {exc}",
            })
        except ToolNotFoundError as exc:
            self._pipeline_repo.finish_run(run_id, "failed", error={
                "kind": "user",
                "message": f"第 {next_index} 步工具不可用: {exc}",
            })

    def get_run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        return self._task_repo.list_by_pipeline_run(run_id)
