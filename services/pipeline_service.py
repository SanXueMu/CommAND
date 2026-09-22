"""L4 管线编排：定义注册 / 运行提交 / 终态推进（由 scheduler 钩子驱动）。"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import resolve_input
from services.dispatch_service import DispatchService
from services.batch_rerun_service import BatchRerunService
from services.run_artifact_service import RunArtifactService
from services.pipeline_definition_service import PipelineDefinitionService
from services.run_lifecycle_service import RunLifecycleService
from services.run_recovery_service import RunRecoveryService
from services.run_query_service import RunQueryService
from services.run_step_coordinator import RunStepCoordinator
from services.step_rerun_service import StepRerunService
from services.subrun_cascade_coordinator import SubrunCascadeCoordinator
from services.subrun_coordinator import SubrunCoordinator
from store.db import Db
from store.key_repo import KeyRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

logger = logging.getLogger("command.pipeline")

# 删除运行中的 run 时：中止后等待活跃任务收口的秒数（超时仍删，pending 回报）
DELETE_ABORT_WAIT_S = 10.0
# 能力不可用（模型未开通/无权限/额度）且**没有**可降级等价流时的可操作提示：
# 把 run 标为 paused，用户换好密钥后点「继续」即可重试原流。
_UNAVAILABLE_HINT = (
    "该密钥/模型当前不可用（未开通、无权限或额度问题）：请在「APIKey管理」确认密钥已开通该模型，"
    "换好密钥后点「继续」重试；若该密钥确实没有该模型权限，请改用其它处理方式"
    "（例如把图片转为 PDF 后用「版式翻译」）"
)


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
        data_dir: Path | None = None,
        key_repo: KeyRepo | None = None,
        definition_service: PipelineDefinitionService | None = None,
        lifecycle_service: RunLifecycleService | None = None,
    ) -> None:
        self._db = db
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._dispatch = dispatch_service
        self._run_events = run_event_repo
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._key_repo = key_repo
        self._definitions = definition_service or PipelineDefinitionService(
            pipeline_repo=pipeline_repo, tool_repo=tool_repo, key_repo=key_repo)
        self._lifecycle = lifecycle_service or RunLifecycleService(
            pipeline_repo=pipeline_repo, dispatch_service=dispatch_service,
            run_event_repo=run_event_repo)
        self._recovery = RunRecoveryService(
            pipeline_repo=pipeline_repo, run_event_repo=run_event_repo,
            submit=self._submit, spawn_subrun=self._spawn_subrun,
            finish_and_cascade=self._finish_and_cascade, resume=self.resume_run)
        self._step_rerun = StepRerunService(
            pipeline_repo=pipeline_repo, run_event_repo=run_event_repo,
            cancel=self._dispatch.cancel, submit=self._submit)
        self._queries = RunQueryService(
            pipeline_repo=pipeline_repo, task_repo=task_repo, run_event_repo=run_event_repo)
        self._artifacts = RunArtifactService(
            pipeline_repo, task_repo, data_dir, self._run_tree_ids, self.list_runs)
        self._step_coordinator = RunStepCoordinator(
            pipeline_repo=pipeline_repo, run_event_repo=run_event_repo,
            submit=self._submit, spawn_subrun=self._spawn_subrun,
            finish_and_cascade=self._finish_and_cascade)
        self._subruns = SubrunCoordinator(
            pipeline_repo=pipeline_repo, run_event_repo=run_event_repo,
            submit=self._submit)
        self._subrun_cascade = SubrunCascadeCoordinator(
            pipeline_repo=pipeline_repo, run_event_repo=run_event_repo,
            finish_and_cascade=self._finish_and_cascade, advance=self.advance)

    def register(self, pipeline_id: str, name: str, steps: list[dict[str, Any]],
                 doc_md: str | None = None, input_schema: dict[str, Any] | None = None,
                 on_failure: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._definitions.register(
            pipeline_id, name, steps, doc_md=doc_md, input_schema=input_schema,
            on_failure=on_failure)

    def list(self) -> list[dict[str, Any]]:
        return self._definitions.list()

    def delete(self, pipeline_id: str) -> dict[str, Any]:
        return self._definitions.delete(pipeline_id)

    def get(self, pipeline_id: str) -> dict[str, Any]:
        return self._definitions.get(pipeline_id)

    def _validate_key_name(self, input_: dict[str, Any] | None) -> None:
        self._definitions.validate_key_name(input_)

    def run(self, pipeline_id: str, input: dict[str, Any],
            batch_id: str | None = None,
            fallback_of: str | None = None) -> dict[str, Any]:
        self._validate_key_name(input)
        definition = self.get(pipeline_id)
        run_id = self._pipeline_repo.create_run(pipeline_id, input, batch_id=batch_id,
                                                fallback_of=fallback_of)
        self._audit(run_id, None, "created", detail={"pipeline_id": pipeline_id})
        first = definition["steps"][0]
        try:
            if "pipeline" in first:  # C1：工作流首步即子流 → 直接创建子 run
                self._spawn_subrun(run_id, 0, first, {"input": input}, None, {})
            else:
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
            "first_handle": submitted["handle"] if "pipeline" not in first else None,
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

    def _spawn_subrun(self, parent_run_id: str, step_index: int, step: dict[str, Any],
                      run: dict[str, Any], prev_output: Any,
                      history: dict[int, Any]) -> dict[str, Any]:
        return self._subruns.spawn(parent_run_id, step_index, step, run, prev_output, history)

    def _fallback_flow_for(self, run: dict[str, Any] | None, status: str,
                           error: dict[str, Any] | None) -> str | None:
        """失败降级判定：**能力不可用**（模型未开通/无权限）且该流声明了 on_failure.fallback_flow。

        只对顶层 run 生效、且降级 run 自身不再降级（fallback_of 非空），避免链式/循环降级。
        """
        if run is None or status != "failed" or not error:
            return None
        if str(error.get("kind") or "") != "unavailable":
            return None
        if run.get("parent_run_id") or run.get("fallback_of"):
            return None
        definition = self._pipeline_repo.get_definition(str(run.get("pipeline_id"))) or {}
        flow = (definition.get("on_failure") or {}).get("fallback_flow")
        return flow if isinstance(flow, str) and flow else None

    def _should_pause_instead(self, run: dict[str, Any] | None, status: str,
                              error: dict[str, Any] | None) -> bool:
        """能力不可用且该流**没有**可降级的等价流 → 把 run 标为 paused（而非 failed）。

        这样用户换好密钥后点「继续」即可**重试原流**；否则会留下一条红色失败记录，
        而且（若降级到 skip 流）文件会被永久标记为「不翻译」、再也无法重试。
        只对顶层 run 生效（子 run 仍走失败级联）。
        """
        if run is None or status != "failed" or not error:
            return False
        if str(error.get("kind") or "") != "unavailable":
            return False
        return run.get("parent_run_id") is None and not run.get("fallback_of")

    def _finish_and_cascade(self, run_id: str, status: str,
                            error: dict[str, Any] | None = None) -> None:
        """07 级联收口：run 终态化；子 run 成功→合成任务喂父 advance（推进父下一步）；
        子 run 失败→父同状态收口（部件失败=整流失败）。

        另外承担「失败降级」：能力不可用且声明了 fallback_flow → 原 run 留 failed 并注明，
        同时**新起一条降级 run**（同 input/batch_id，记 fallback_of），交付物由降级 run 产出。
        """
        run = self._pipeline_repo.get_run(run_id)
        fallback_flow = self._fallback_flow_for(run, status, error)
        if fallback_flow:
            error = dict(error or {})
            error["message"] = (f"{error.get('message', '')}"
                               f"（能力不可用，已自动改用「{fallback_flow}」重跑）")
            error["fallback_flow"] = fallback_flow
        if not fallback_flow and self._should_pause_instead(run, status, error):
            error = dict(error or {})
            error["message"] = f"{error.get('message', '')}（能力不可用，已暂停：{_UNAVAILABLE_HINT}）"
            error["hint"] = _UNAVAILABLE_HINT
            error["paused_unavailable"] = True
            self._pipeline_repo.finish_run(run_id, "paused", error=error)
            return
        self._pipeline_repo.finish_run(run_id, status, error=error)
        self._purge_decisive(run_id, status, error, fallback_flow is not None)
        if fallback_flow and run is not None:
            try:
                fb_input = dict(run.get("input") or {})
                # 降级目标若声明了 reason（如「暂不翻译」流），把降级原因写进去：
                # 否则记录只显示工具默认文案（「本轮不处理」），看不出为何被跳过
                fb_def = self._pipeline_repo.get_definition(fallback_flow) or {}
                if "reason" in ((fb_def.get("input_schema") or {}).get("properties") or {}):
                    fb_input["reason"] = (
                        f"上游「{run.get('pipeline_id')}」能力不可用（{(error or {}).get('message', '')}），"
                        f"已自动降级为不翻译留档；如需翻译请修复密钥/模型后重跑")
                created = self.run(fallback_flow, fb_input,
                                   batch_id=run.get("batch_id"), fallback_of=run_id)
                self._audit(run_id, None, "run_fallback",
                            detail={"to_run": created["run_id"], "fallback_flow": fallback_flow})
                self._audit(created["run_id"], None, "run_fallback",
                            detail={"from_run": run_id, "fallback_flow": fallback_flow})
            except Exception:  # noqa: BLE001 —— 降级失败不掩盖原 run 的失败原因
                logger.exception("失败降级启动失败 run=%s fallback=%s", run_id, fallback_flow)
        self._subrun_cascade.cascade(run_id, status, error)

    def advance(self, task: dict[str, Any]) -> None:
        self._step_coordinator.advance(task)

    # ---- 流的全控制三原语（方案 §5） -----------------------------------

    def pause_run(self, run_id: str) -> dict[str, Any]:
        return self._lifecycle.pause(run_id)

    def recover_stale_runs(self) -> list[str]:
        """AF2：启动收口——进程重启后库内仍 running 的 run 已无人推进，统一标 interrupted。

        用户裁定：不做时间窗超时（上百页 PDF 逐页识别慢是常态，不误伤）——只按
        **进程存活**判定：本方法只在 lifespan 启动时调用，此刻内存无任何活跃 run，
        库里的 running 必然是上次进程死亡留下的。事件留痕、可重跑（interrupted 在
        RERUNNABLE_STATUSES 内）；paused 不动（那是「可继续」语义，与进程无关）。
        """
        return self._lifecycle.recover_stale()

    def resume_run(self, run_id: str) -> dict[str, Any]:
        return self._recovery.resume_run(run_id)

    def abort_run(self, run_id: str) -> dict[str, Any]:
        return self._lifecycle.abort(run_id)

    def abort_step(self, run_id: str, step_index: int) -> dict[str, Any]:
        return self._lifecycle.abort_step(run_id, step_index)

    def rerun_step(self, run_id: str, step_index: int,
                   override: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._step_rerun.rerun_step(run_id, step_index, override)

    def rerun_run(self, run_id: str, input_override: dict[str, Any] | None = None,
                  keep_batch: bool = True) -> dict[str, Any]:
        """C4 重跑流（06 四.1）：原 run 留档不可变，以 run.input + 覆盖起全新 run；
        workflow 重跑自然重建子 run 树。仅终态 run 可重跑。

        keep_batch：新 run 继承原 run 的 batch_id（默认）——否则重跑后脱离批次，
        批次导出按 batch_id 取 run 时会看不到这条，译文会被判为缺失。
        """
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        if run["status"] in ("running", "paused"):
            raise TaskConflictError(f"run 未终态，不可重跑: {run['status']}")
        new_input = dict(run["input"] or {})
        new_input.update(input_override or {})
        self._validate_key_name(new_input)
        # 先建新 run 再补写审计（flow_rerun 需回填 new_run_id）
        new_run_id = self._pipeline_repo.create_run(
            run["pipeline_id"], new_input,
            batch_id=run.get("batch_id") if keep_batch else None)
        self._audit(run_id, None, "flow_rerun",
                    detail={"new_run_id": new_run_id,
                            "override": sorted(input_override) if input_override else []})
        self._audit(new_run_id, None, "created",
                    detail={"pipeline_id": run["pipeline_id"], "rerun_of": run_id})

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        first = definition["steps"][0]
        try:
            if "pipeline" in first:
                self._spawn_subrun(new_run_id, 0, first, {"input": new_input}, None, {})
                first_handle = None
            else:
                resolved = resolve_input(first["input"], new_input, None, {})
                first_handle = self._submit(definition, new_run_id, 0, resolved)["handle"]
        except ToolUserError as exc:
            self._finish_and_cascade(new_run_id, "failed", error={
                "kind": "user", "message": f"重跑流首步无法入队: {exc}"})
            raise
        except ToolNotFoundError as exc:
            self._finish_and_cascade(new_run_id, "failed", error={
                "kind": "user", "message": f"重跑流首步工具不可用: {exc}"})
            raise
        return {"run_id": new_run_id, "rerun_of": run_id, "status": "running",
                "first_handle": first_handle}

    RERUNNABLE_STATUSES = BatchRerunService.RERUNNABLE_STATUSES

    def _batch_rerun_service(self) -> BatchRerunService:
        # 每次取当前 rerun_run，保留轻量测试和调用方替换入口的兼容性。
        return BatchRerunService(self._pipeline_repo, self.rerun_run)

    @staticmethod
    def _dedupe_by_file(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return BatchRerunService.dedupe_by_file(runs)

    def rerun_runs(self, run_ids: list[str]) -> dict[str, Any]:
        return self._batch_rerun_service().rerun_runs(run_ids)

    def failed_runs_of_batch(self, batch_id: str, limit: int = 500) -> list[str]:
        return self._batch_rerun_service().failed_runs_of_batch(batch_id, limit)

    def best_runs_of_batch(self, batch_id: str) -> list[dict[str, Any]]:
        return self._batch_rerun_service().best_runs_of_batch(batch_id)

    def rerunnable_runs(self, batch_id: str | None = None, flow_ids: list[str] | None = None,
                        limit: int = 1000) -> dict[str, Any]:
        return self._batch_rerun_service().rerunnable_runs(batch_id, flow_ids, limit)

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        return self._queries.run_snapshot(run_id)

    def list_run_events(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return self._queries.list_run_events(run_id, limit)

    def get_run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        return self._queries.get_run_tasks(run_id)

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50,
                  offset: int = 0, batch_id: str | None = None) -> dict[str, Any]:
        return self._queries.list_runs(pipeline_id, limit, offset, batch_id)

    def _run_summary(self, run: dict[str, Any]) -> dict[str, Any]:
        return self._queries._run_summary(run)

    def detail_summary(self, run_id: str) -> dict[str, Any] | None:
        return self._queries.detail_summary(run_id)

    def _summaries(self, runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self._queries._summaries(runs)

    def delete_run(self, run_id: str, purge_files: bool = True) -> dict[str, Any]:
        """删除任务（含审计事件）；`purge_files` 连带删除其全部产物目录（结果与临时结果随任务绑定）。

        AD1：OCR 结果库（data/ocr/*.ocr_results.db 及其 .raw.json 留痕）不在 outputs 目录，
        需单独收集清理；被树外其它 run 引用的库跳过（防显式同名库误删）。

        AF1：purge_files=true 时 ①树内 tasks 整删（不再解绑留孤儿引用）②**同原件文件的
        全部失败态 run（含任务清单窗口外的旧尝试）一并删除**——成功 run 不动（有交付物），
        rerunnable 计数随之归零。purge_files=false 保持解绑审计口径。

        运行中/暂停 → 先自动中止（cancelled 立即落库）并等待活跃任务收口（≤DELETE_ABORT_WAIT_S），
        超时仍继续删除，pending 列表回报给调用方（避免与 worker 竞态）。
        """
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        aborted = False
        pending: list[str] = []
        if run["status"] in ("running", "paused"):
            self.abort_run(run_id)
            aborted = True
            deadline = time.monotonic() + DELETE_ABORT_WAIT_S
            while time.monotonic() < deadline:
                pending = self._pipeline_repo.active_task_handles(run_id)
                if not pending:
                    break
                time.sleep(0.5)
        tree_ids = self._run_tree_ids(run_id)
        handles = [t["handle"] for rid in tree_ids
                   for t in self._task_repo.list_by_pipeline_run(rid)]
        purged = self._purge_artifacts(handles) if purge_files else {
            "files_removed": 0, "bytes_freed": 0, "dirs_removed": 0}
        ocr_purged = purge_ocr_dbs(self._pipeline_repo, self._data_dir, tree_ids) \
            if purge_files else {"dbs_removed": 0, "dbs_shared": []}
        self._pipeline_repo.delete_run(run_id, drop_tasks=purge_files)

        removed_failed: list[dict] = []
        if purge_files:  # AF1：同文件失败尝试连带清理
            file_key = str((run.get("input") or {}).get("file") or "")
            if file_key:
                doomed = self._pipeline_repo.failed_runs_by_file(file_key, exclude_ids=tree_ids)
                for stale in doomed:
                    stale_tree = self._run_tree_ids(stale["id"])
                    stale_handles = [t["handle"] for rid in stale_tree
                                     for t in self._task_repo.list_by_pipeline_run(rid)]
                    stale_purged = self._purge_artifacts(stale_handles)
                    purged["files_removed"] += stale_purged.get("files_removed", 0)
                    purged["bytes_freed"] += stale_purged.get("bytes_freed", 0)
                    stale_ocr = purge_ocr_dbs(self._pipeline_repo, self._data_dir, stale_tree)
                    ocr_purged["dbs_removed"] += stale_ocr.get("dbs_removed", 0)
                    ocr_purged["dbs_shared"].extend(stale_ocr.get("dbs_shared", []))
                    self._pipeline_repo.delete_run(stale["id"], drop_tasks=True)
                    removed_failed.append(stale)
        return {"id": run_id, "status": "deleted", "aborted": aborted,
                "pending_tasks": pending, "purge_files": purge_files, **purged, **ocr_purged,
                "removed_failed_attempts": removed_failed}

    def _run_tree_ids(self, run_id: str) -> list[str]:
        """run 及其全部子 run（workflow 的 pipeline 步产物也随父任务绑定）。"""
        ids = [run_id]
        seen = {run_id}
        queue = [run_id]
        while queue:
            current = queue.pop()
            for sub in self._pipeline_repo.get_subruns(current).values():
                if sub["id"] not in seen:
                    seen.add(sub["id"])
                    ids.append(sub["id"])
                    queue.append(sub["id"])
        return ids

    # AF3：决定性错误 = 重试无意义（用户参数/用法错 user、模型能力不可用 unavailable）。
    # 此类失败收口时自动清产物（含 OCR 库与 raw.json），只留 run/error/事件供排查；
    # 暂时性错误（system/domain/网络类）保留产物，供「重跑失败项」续上页级缓存。
    DECISIVE_ERROR_KINDS = {"user", "unavailable"}

    def _purge_decisive(self, run_id: str, status: str,
                        error: dict[str, Any] | None, fallback: bool) -> None:
        if status != "failed" or fallback:
            return
        kind = str((error or {}).get("kind") or "")
        if kind not in self.DECISIVE_ERROR_KINDS:
            return
        try:
            tree_ids = self._run_tree_ids(run_id)
            handles = [t["handle"] for rid in tree_ids
                       for t in self._task_repo.list_by_pipeline_run(rid)]
            purged = self._purge_artifacts(handles)
            ocr = purge_ocr_dbs(self._pipeline_repo, self._data_dir, tree_ids)
            self._audit(run_id, None, "artifacts_purged", detail={
                "reason": f"decisive:{kind}", **purged, **ocr})
        except Exception:  # noqa: BLE001 —— 清产物失败不掩盖失败原因本身
            logger.exception("决定性错误清理产物失败 run=%s", run_id)

    def collect_run_artifacts(self, run_id: str, scope: str = "final") -> list[dict[str, Any]]:
        return self._artifacts.collect(run_id, scope)

    def run_artifact_usage(self, run_id: str) -> dict[str, int]:
        return self._artifacts.usage(run_id)

    def usage_report(self, run_ids: list[str] | None = None, pipeline_id: str | None = None,
                     limit: int = 50) -> dict[str, Any]:
        return self._artifacts.usage_report(run_ids, pipeline_id, limit)

    def _purge_artifacts(self, handles: list[str]) -> dict[str, int]:
        """删除任务产物目录 `data/outputs/<handle>/`（最终产物与中间临时产物一并清）。"""
        empty = {"files_removed": 0, "bytes_freed": 0, "dirs_removed": 0}
        if self._data_dir is None or not handles:
            return empty
        root = (self._data_dir / "outputs")
        if not root.is_dir():
            return empty
        root = root.resolve()
        files_removed = bytes_freed = dirs_removed = 0
        for handle in handles:
            target = (root / str(handle)).resolve()
            if root not in target.parents or not target.is_dir():  # 防越界与符号链接逃逸
                continue
            for path in target.rglob("*"):
                if path.is_file():
                    try:
                        bytes_freed += path.stat().st_size
                    except OSError:
                        pass
                    files_removed += 1
            shutil.rmtree(target, ignore_errors=True)
            dirs_removed += 1
        return {"files_removed": files_removed, "bytes_freed": bytes_freed,
                "dirs_removed": dirs_removed}


def _iter_output_strings(value: Any):
    """递归取出 output 里全部字符串值（dict 键值/列表元素）。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_output_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_output_strings(v)


def purge_ocr_dbs(repo: PipelineRepo, data_dir: Path | None, tree_ids: list[str]) -> dict:
    """AD1：清理 run 树的 OCR 结果库（*.ocr_results.db 及其 .raw.json 留痕）。

    只动 data_dir 内、后缀匹配的文件；被树外 run 的任务输出引用的库跳过（dbs_shared 回报），
    防止用户显式同名库被连带误删。
    """
    empty = {"dbs_removed": 0, "dbs_shared": []}
    if data_dir is None or not tree_ids:
        return empty
    root = data_dir.resolve()
    candidates: set[str] = set()
    for rid in tree_ids:
        for output in (repo.outputs_by_step(rid) or {}).values():
            for text in _iter_output_strings(output):
                if text.endswith(".ocr_results.db") or text.endswith(".ocr_results.db.raw.json"):
                    candidates.add(text)
    removed = 0
    shared: list[str] = []
    for raw_path in sorted(candidates):
        path = Path(raw_path)
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if root != resolved and root not in resolved.parents:
            continue  # data 目录之外不动
        if repo.db_referenced_outside(str(path), tree_ids):
            shared.append(str(path))
            continue
        try:
            resolved.unlink()
            removed += 1
        except OSError:
            pass
    return {"dbs_removed": removed, "dbs_shared": shared}
