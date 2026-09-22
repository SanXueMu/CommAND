"""运行生命周期服务：暂停、恢复收口和中止运行。"""

from __future__ import annotations

from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError
from services.dispatch_service import DispatchService
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo

RUN_TERMINAL = {"succeeded", "failed", "failed_review", "cancelled", "interrupted"}


class RunLifecycleService:
    """只负责 run 状态迁移和取消意图，不负责下一步编排。"""

    def __init__(self, pipeline_repo: PipelineRepo, dispatch_service: DispatchService,
                 run_event_repo: RunEventRepo | None = None) -> None:
        self._pipeline_repo = pipeline_repo
        self._dispatch = dispatch_service
        self._run_events = run_event_repo

    def pause(self, run_id: str) -> dict[str, Any]:
        """温和暂停：当前节点完成后停在边界；已在边界则立即生效。"""
        run = self._require_run(run_id)
        if run["status"] in RUN_TERMINAL:
            raise TaskConflictError(f"run 已终态，无法暂停: {run['status']}")
        if self._pipeline_repo.cas_run_status(run_id, ("running",), "paused"):
            self._audit(run_id, "pause_requested", detail={"from": "running"})
            return {"run_id": run_id, "status": "paused"}
        return {"run_id": run_id, "status": "paused"}

    def recover_stale(self) -> list[str]:
        """进程启动时收口上次遗留的 running run。"""
        recovered: list[str] = []
        for run_id in self._pipeline_repo.running_run_ids():
            self._pipeline_repo.finish_run_forced(
                run_id, "interrupted",
                error={"message": "进程重启中断，可重跑", "kind": "transient"})
            self._audit(run_id, "run_recovered",
                        detail={"reason": "process_restart", "status": "interrupted"})
            recovered.append(run_id)
        return recovered

    def abort(self, run_id: str) -> dict[str, Any]:
        """立即中止 run 及其活跃子 run，成果保留。"""
        run = self._require_run(run_id)
        if not self._pipeline_repo.cas_run_status(
                run_id, ("running", "paused"), "cancelled"):
            raise TaskConflictError(f"run 已终态: {run['status']}")
        self._audit(run_id, "abort_requested")
        for handle in self._pipeline_repo.active_task_handles(run_id):
            try:
                self._dispatch.cancel(handle)
            except Exception:  # noqa: BLE001 取消尽力而为，收口为准
                pass
        for sub in self._pipeline_repo.get_subruns(run_id).values():
            if sub["status"] in ("running", "paused"):
                try:
                    self.abort(sub["id"])
                except TaskConflictError:
                    pass
        self._audit(run_id, "run_aborted")
        return {"run_id": run_id, "status": "cancelled"}

    def abort_step(self, run_id: str, step_index: int) -> dict[str, Any]:
        """中止单个活跃步骤，不改变 run 状态。"""
        self._require_run(run_id)
        task = self._pipeline_repo.latest_task_by_step(run_id).get(step_index)
        if task is None:
            raise TaskNotFoundError(f"第 {step_index} 步尚无任务")
        if task["status"] not in ("queued", "running"):
            raise TaskConflictError(f"第 {step_index} 步不可中止（已 {task['status']}）")
        result = self._dispatch.cancel(task["handle"])
        self._audit(run_id, "step_abort", task["handle"],
                    detail={"step_index": step_index, "result": result.get("status")})
        return {"run_id": run_id, "step_index": step_index, **result}

    def _require_run(self, run_id: str) -> dict[str, Any]:
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        return run

    def _audit(self, run_id: str, kind: str, task_handle: str | None = None,
               detail: dict[str, Any] | None = None) -> None:
        if self._run_events is not None:
            self._run_events.append(run_id, task_handle, kind, detail=detail)
