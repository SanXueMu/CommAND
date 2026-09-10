"""L4 管线编排：定义注册 / 运行提交 / 终态推进（由 scheduler 钩子驱动）。"""

from __future__ import annotations

import re
from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import resolve_input
from services.dispatch_service import DispatchService
from store.db import Db
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

PIPELINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

FAILURE_STATUSES = {"failed", "failed_review", "cancelled", "interrupted"}
RUN_TERMINAL = {"succeeded", "failed", "failed_review", "cancelled", "interrupted"}


class PipelineService:
    """线性管线：首步提交 → 每步 succeeded 后解析模板入队下步 → 终态收口。

    流的全控制（方案：架构升级-流的全控制.md）：
    pause/resume/abort 三原语 + advance 派发门（节点边界拦截）+ run_events 全程审计。
    """

    def __init__(
        self,
        db: Db,
        pipeline_repo: PipelineRepo,
        task_repo: TaskRepo,
        tool_repo: ToolRepo,
        dispatch_service: DispatchService,
        run_event_repo: RunEventRepo | None = None,
    ) -> None:
        self._db = db
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._dispatch = dispatch_service
        self._run_events = run_event_repo

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

    def delete(self, pipeline_id: str) -> dict[str, Any]:
        if self._pipeline_repo.get_definition(pipeline_id) is None:
            raise TaskNotFoundError(f"管线不存在: {pipeline_id}")
        active = self._pipeline_repo.count_active_runs(pipeline_id)
        if active:
            raise ToolUserError(f"管线有 {active} 个运行中/暂停的 run，先终止再删除")
        self._pipeline_repo.delete_definition(pipeline_id)
        return {"id": pipeline_id, "status": "deleted"}

    def get(self, pipeline_id: str) -> dict[str, Any]:
        definition = self._pipeline_repo.get_definition(pipeline_id)
        if definition is None:
            raise TaskNotFoundError(f"管线不存在: {pipeline_id}")
        return definition

    def run(self, pipeline_id: str, input: dict[str, Any]) -> dict[str, Any]:
        definition = self.get(pipeline_id)
        run_id = self._pipeline_repo.create_run(pipeline_id, input)
        self._audit(run_id, None, "created", detail={"pipeline_id": pipeline_id})
        first = definition["steps"][0]
        try:
            resolved = resolve_input(first["input"], input, None, {})
            submitted = self._submit(definition, run_id, 0, resolved)
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

    def _submit(self, definition: dict[str, Any], run_id: str, step_index: int,
                resolved_input: dict[str, Any]) -> dict[str, Any]:
        """派发单步并落审计（step_queued）。"""
        step = definition["steps"][step_index]
        submitted = self._dispatch.submit(step["tool"], resolved_input,
                                          pipeline_run=run_id, step_index=step_index)
        self._audit(run_id, submitted.get("handle"), "step_queued",
                    detail={"step_index": step_index, "tool": step["tool"]})
        return submitted

    def _audit(self, run_id: str | None, task_handle: str | None, kind: str,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None and run_id:
            self._run_events.append(run_id, task_handle, kind, detail=detail)

    def advance(self, task: dict[str, Any]) -> None:
        """scheduler 终态钩子：succeeded → 推进下步；失败终态 → run 收口。幂等。"""
        run_id = task.get("pipeline_run")
        if not run_id:
            return
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            return
        if run["status"] == "paused":
            # 派发门：跑完当前节点后停在边界（progress 指针 + 审计），等待 resume
            if task["status"] == "succeeded":
                self._pipeline_repo.set_run_progress(run_id, task["step_index"] + 1)
                self._audit(run_id, task["handle"], "paused_at_boundary",
                            detail={"next_index": task["step_index"] + 1})
            return
        if run["status"] != "running":
            return
        if task["status"] in FAILURE_STATUSES:
            self._audit(run_id, task["handle"], "step_failed",
                        detail={"step_index": task["step_index"], "status": task["status"]})
            self._pipeline_repo.finish_run(run_id, task["status"], error=task.get("error"))
            return
        if task["status"] != "succeeded":
            return
        self._audit(run_id, task["handle"], "step_completed",
                    detail={"step_index": task["step_index"]})

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
            self._submit(definition, run_id, next_index, resolved)
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

    # ---- 流的全控制三原语（方案 §5） -----------------------------------

    def pause_run(self, run_id: str) -> dict[str, Any]:
        """温和暂停：标记意图，当前节点跑完后停在边界；若已在边界则立即生效。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if run["status"] in RUN_TERMINAL:
            raise TaskConflictError(f"run 已终态，无法暂停: {run['status']}")
        if self._pipeline_repo.cas_run_status(run_id, ("running",), "paused"):
            self._audit(run_id, None, "pause_requested", detail={"from": "running"})
            return {"run_id": run_id, "status": "paused"}
        return {"run_id": run_id, "status": "paused"}  # 已是 paused，幂等

    def resume_run(self, run_id: str) -> dict[str, Any]:
        """恢复即查询（重放）：定位首个未成功步骤分派；已 succeeded 步骤永不重发。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if not self._pipeline_repo.cas_run_status(run_id, ("paused",), "running"):
            if run["status"] == "running":
                return {"run_id": run_id, "status": "running"}  # 幂等
            raise TaskConflictError(f"run 状态不可恢复: {run['status']}")
        self._audit(run_id, None, "resume_requested")

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        history = self._pipeline_repo.outputs_by_step(run_id)
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        dispatched: dict[str, Any] | None = None

        for n, step in enumerate(steps):
            t = latest.get(n)
            if t is None:
                prev_output = history.get(n - 1)
                try:
                    resolved = resolve_input(step["input"], run["input"], prev_output, history)
                    dispatched = self._submit(definition, run_id, n, resolved)
                except (ToolUserError, ToolNotFoundError) as exc:
                    self._pipeline_repo.finish_run(run_id, "failed", error={
                        "kind": "user", "message": f"恢复时第 {n} 步无法入队: {exc}"})
                break
            if t["status"] in ("queued", "running"):
                break  # 暂停期间仍有活任务，等它终态触发 advance
            if t["status"] == "succeeded":
                if n == len(steps) - 1:
                    self._pipeline_repo.finish_run(run_id, "succeeded")
                continue
            # cancelled / interrupted / failed*：以留档 input 从断点重发本步
            try:
                resolved = dict(t["input"])
                dispatched = self._submit(definition, run_id, n, resolved)
            except ToolNotFoundError as exc:
                self._pipeline_repo.finish_run(run_id, "failed", error={
                    "kind": "user", "message": f"恢复时第 {n} 步工具不可用: {exc}"})
                break
            break

        self._audit(run_id, None, "resumed",
                    detail={"dispatched": dispatched["handle"] if dispatched else None})
        return {"run_id": run_id, "status": "running",
                "dispatched": dispatched["handle"] if dispatched else None}

    def abort_run(self, run_id: str) -> dict[str, Any]:
        """立即中止：活跃任务全部发起取消，run 强制收口为 cancelled；成果留档可查。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if not self._pipeline_repo.cas_run_status(
                run_id, ("running", "paused"), "cancelled"):
            raise TaskConflictError(f"run 已终态: {run['status']}")
        self._audit(run_id, None, "abort_requested")
        for handle in self._pipeline_repo.active_task_handles(run_id):
            try:
                self._dispatch.cancel(handle)
            except Exception:  # noqa: BLE001 取消尽力而为，收口为准
                pass
        self._audit(run_id, None, "run_aborted")
        return {"run_id": run_id, "status": "cancelled"}

    def abort_step(self, run_id: str, step_index: int) -> dict[str, Any]:
        """节点中止：queued/running 任务发起取消；run 状态不变（等收口或人工 rerun）。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        task = latest.get(step_index)
        if task is None:
            raise TaskNotFoundError(f"第 {step_index} 步尚无任务")
        if task["status"] not in ("queued", "running"):
            raise TaskConflictError(f"第 {step_index} 步不可中止（已 {task['status']}）")
        result = self._dispatch.cancel(task["handle"])
        self._audit(run_id, task["handle"], "step_abort",
                    detail={"step_index": step_index, "result": result.get("status")})
        return {"run_id": run_id, "step_index": step_index, **result}

    def rerun_step(self, run_id: str, step_index: int,
                   override: dict[str, Any] | None = None) -> dict[str, Any]:
        """断点重跑（Translee 痛点解药）：留档 input 为底 + 字段级覆盖；
        后续步骤排队中任务取消、已完成保留（取代关系记录于审计）；run 复活为 running。"""
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

        # CAS 复活：paused/任意终态 → running（并发 rerun 只赢一个）
        if not self._pipeline_repo.cas_run_status(
                run_id, tuple(s for s in ("paused", "succeeded", "failed",
                                          "failed_review", "cancelled", "interrupted")),
                "running"):
            raise TaskConflictError(f"run 状态不可重跑: {run['status']}")
        self._audit(run_id, None, "rerun_requested",
                    detail={"step_index": step_index, "override": override or {}})
        if override:
            self._audit(run_id, task["handle"] if task else None, "override_applied",
                        detail={"step_index": step_index, "fields": sorted(override)})

        # 后续步骤的活跃任务取消（已完成保留，推进以最新任务为准）
        for later in (h for i, t in latest.items() if i > step_index
                      for h in [t["handle"]] if t["status"] in ("queued", "running")):
            try:
                self._dispatch.cancel(later)
            except Exception:  # noqa: BLE001
                pass

        # 留档 input 为底（无历史任务则模板解析）+ override 合并
        if task is not None:
            resolved = dict(task["input"] or {})
            resolved.update(override or {})
        else:
            history = self._pipeline_repo.outputs_by_step(run_id)
            prev_output = history.get(step_index - 1)
            resolved = resolve_input(steps[step_index]["input"], run["input"],
                                     prev_output, history)
            resolved.update(override or {})
        try:
            submitted = self._submit(definition, run_id, step_index, resolved)
        except ToolNotFoundError as exc:
            self._pipeline_repo.finish_run(run_id, "failed", error={
                "kind": "user", "message": f"重跑第 {step_index} 步工具不可用: {exc}"})
            raise
        self._audit(run_id, submitted["handle"], "step_rerun",
                    detail={"step_index": step_index,
                            "attempt": submitted.get("attempt", 1)})
        return {"run_id": run_id, "step_index": step_index,
                "handle": submitted["handle"], "status": "running"}

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        """steps 快照：每步最新任务 + 定义工具名（工作区/任务中心的考证视图）。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        steps = []
        for n, step in enumerate(definition["steps"]):
            t = latest.get(n)
            steps.append({
                "step_index": n,
                "tool": step["tool"],
                "latest": t,
            })
        return {"run": run, "steps": steps}

    def list_run_events(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if self._run_events is None:
            return []
        return self._run_events.list(run_id, limit)

    def get_run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        return self._task_repo.list_by_pipeline_run(run_id)
