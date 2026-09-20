"""L4 管线编排：定义注册 / 运行提交 / 终态推进（由 scheduler 钩子驱动）。"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError
from core.pipeline import evaluate_when, resolve_input, validate_when
from services.dispatch_service import DispatchService
from store.db import Db
from store.key_repo import KeyRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo

logger = logging.getLogger("command.pipeline")

PIPELINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

FAILURE_STATUSES = {"failed", "failed_review", "cancelled", "interrupted"}
RUN_TERMINAL = {"succeeded", "failed", "failed_review", "cancelled", "interrupted"}
# 删除运行中的 run 时：中止后等待活跃任务收口的秒数（超时仍删，pending 回报）
DELETE_ABORT_WAIT_S = 10.0
# 可打包下载的产物后缀（文档类；排除 .json/.db 等中间态文件）
ARTIFACT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".csv", ".zip"}

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
    ) -> None:
        self._db = db
        self._pipeline_repo = pipeline_repo
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._dispatch = dispatch_service
        self._run_events = run_event_repo
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._key_repo = key_repo

    def register(self, pipeline_id: str, name: str, steps: list[dict[str, Any]],
                 doc_md: str | None = None, input_schema: dict[str, Any] | None = None,
                 on_failure: dict[str, Any] | None = None) -> dict[str, Any]:
        if not PIPELINE_ID_PATTERN.match(pipeline_id):
            raise ToolUserError(f"管线 id 须为点分多段（小写）: {pipeline_id}")
        if not steps or not isinstance(steps, list):
            raise ToolUserError("steps 须为非空数组")
        has_sub = False
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "input" not in step:
                raise ToolUserError(f"第 {i} 步须含 input")
            has_tool, has_pipeline = "tool" in step, "pipeline" in step
            if has_tool and has_pipeline:
                raise ToolUserError(f"第 {i} 步 tool 与 pipeline 只能其一")
            if not has_tool and not has_pipeline:
                raise ToolUserError(f"第 {i} 步须含 tool 或 pipeline")
            if has_pipeline:
                has_sub = True
                sub = self._pipeline_repo.get_definition(step["pipeline"])
                if sub is None:
                    raise ToolNotFoundError(f"第 {i} 步引用的流未注册: {step['pipeline']}")
                if sub.get("type") != "flow":
                    raise ToolUserError(
                        f"第 {i} 步只能引用普通流（flow），不可嵌套工作流: {step['pipeline']}")
            elif self._tool_repo.get(step["tool"]) is None:
                raise ToolNotFoundError(f"第 {i} 步工具未注册: {step['tool']}")
            if "when" in step:
                validate_when(step["when"])
            if not isinstance(step["input"], dict):
                raise ToolUserError(f"第 {i} 步 input 须为对象")
        ptype = "workflow" if has_sub else "flow"
        existing = self._pipeline_repo.get_definition(pipeline_id)
        if existing is not None and existing.get("type") != ptype:
            raise ToolUserError(
                f"流类型不可变更: {pipeline_id} 已是 {existing.get('type')}，新定义为 {ptype}")
        # 只拦自降级（会无限循环）；「降级流是否存在」不做注册期校验——注册顺序可能让目标流
        # 尚未注册（如 pdf.image 先于 pdf.layout），存在性由 tests/test_flow_specs.py 静态守卫，
        # 运行期若目标流缺失只记日志、不影响原 run 的失败留档。
        fallback_flow = (on_failure or {}).get("fallback_flow")
        if fallback_flow and str(fallback_flow) == pipeline_id:
            raise ToolUserError("on_failure.fallback_flow 不能是自身（会无限降级）")
        self._pipeline_repo.upsert_definition(pipeline_id, name, steps, doc_md=doc_md,
                                              ptype=ptype, input_schema=input_schema,
                                              on_failure=on_failure)
        return {"id": pipeline_id, "name": name, "type": ptype, "steps": steps,
                "on_failure": on_failure, "status": "registered"}

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

    def _validate_key_name(self, input_: dict[str, Any] | None) -> None:
        """入队前校验 key_name：不在密钥注册表内直接拒绝（避免跑到翻译步才暂停等人工）。

        key_name 缺省（None/空串）表示用默认密钥，放行。
        """
        name = (input_ or {}).get("key_name")
        if not name or not isinstance(name, str):
            return
        if self._key_repo is None:
            return
        known = {str(k.get("name")) for k in self._key_repo.list()}
        if name not in known:
            raise ToolUserError(
                f"密钥不存在: {name}（请先在「设置 → APIKey管理」注册该名称的密钥，"
                f"或留空使用默认密钥）")

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
        """C1：workflow 遇 pipeline 步 → 创建子 run 并派发其首步。
        07 设计：子 run 实体化（parent 两列）；同父步活跃子 run 唯一（008 唯一索引防撞）。"""
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
        self._audit(parent_run_id, None, "subrun_created",
                    detail={"step_index": step_index, "subrun_id": sub_run_id,
                            "pipeline_id": flow_id})
        sub_first = sub_definition["steps"][0]
        sub_resolved = resolve_input(sub_first["input"], resolved, None, {})
        submitted = self._submit(sub_definition, sub_run_id, 0, sub_resolved)
        return {"subrun_id": sub_run_id, "handle": submitted["handle"]}

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
        run = self._pipeline_repo.get_run(run_id)
        if run is None or run["parent_run_id"] is None:
            return
        parent_run_id, step_index = run["parent_run_id"], run["parent_step_index"]
        self._audit(parent_run_id, None, "subrun_finished",
                    detail={"step_index": step_index, "subrun_id": run_id, "status": status})
        if status != "succeeded":
            self._finish_and_cascade(parent_run_id, status, error=error or {
                "kind": "system", "message": f"子流失败（步 {step_index}）"})
            return
        outputs = self._pipeline_repo.outputs_by_step(run_id)
        last_output = outputs[max(outputs)] if outputs else None
        synthetic = {"pipeline_run": parent_run_id, "step_index": step_index,
                     "status": "succeeded", "output": last_output, "error": None,
                     "handle": None, "attempt": 1, "input": run["input"]}
        self.advance(synthetic)

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
        if task["status"] == "paused":
            # 任务级暂停（工具抛 ToolPauseError）：run 停在该步、**不**级联收口；
            # resume 时该步以留档 input 重新派发（见 resume_run 的 cancelled/failed 分支）。
            self._audit(run_id, task["handle"], "step_paused",
                        detail={"step_index": task["step_index"], "error": task.get("error")})
            self._pipeline_repo.cas_run_status(run_id, ("running",), "paused")
            return
        if task["status"] in FAILURE_STATUSES:
            self._audit(run_id, task["handle"], "step_failed",
                        detail={"step_index": task["step_index"], "status": task["status"]})
            self._finish_and_cascade(run_id, task["status"], error=task.get("error"))
            return
        if task["status"] != "succeeded":
            return
        self._audit(run_id, task["handle"], "step_completed",
                    detail={"step_index": task["step_index"]})

        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        steps = definition["steps"]
        history = self._pipeline_repo.outputs_by_step(run_id)
        next_index = task["step_index"] + 1
        prev_output = task["output"]  # prev 语义：最近一个已执行步的输出（skipped 无输出）

        # D2：when 不满足 → 跳步留痕并继续向后探测（全部跳完即收口）
        while next_index < len(steps):
            step = steps[next_index]
            if "when" in step and not evaluate_when(step["when"], run["input"], prev_output, history):
                self._audit(run_id, None, "step_skipped",
                            detail={"step_index": next_index, "when": step["when"]})
                next_index += 1
                continue
            break
        if next_index >= len(steps):
            self._finish_and_cascade(run_id, "succeeded")
            return

        step = steps[next_index]
        if "pipeline" in step:  # C1：workflow 的子流步 → 创建子 run（级联由 _finish_and_cascade 闭环）
            try:
                self._spawn_subrun(run_id, next_index, step, run, prev_output, history)
            except ToolUserError:
                pass  # spawn 内部已收口父 run
            return
        try:
            resolved = resolve_input(step["input"], run["input"], prev_output, history)
            self._submit(definition, run_id, next_index, resolved)
        except ToolUserError as exc:
            self._finish_and_cascade(run_id, "failed", error={
                "kind": "user",
                "message": f"第 {next_index} 步无法入队: {exc}",
            })
        except ToolNotFoundError as exc:
            self._finish_and_cascade(run_id, "failed", error={
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

        skipped = self._run_events.skipped_steps(run_id) if self._run_events else set()
        subruns = self._pipeline_repo.get_subruns(run_id)  # C1：pipeline 步的状态载体是子 run
        for n, step in enumerate(steps):
            if "pipeline" in step:
                sub = subruns.get(n)
                if sub is None:
                    try:
                        prev_output = history.get(n - 1)
                        self._spawn_subrun(run_id, n, step, run, prev_output, history)
                        dispatched = {"handle": None}
                    except (ToolUserError, ToolNotFoundError) as exc:
                        self._finish_and_cascade(run_id, "failed", error={
                            "kind": "user", "message": f"恢复时第 {n} 步子流无法启动: {exc}"})
                    break
                if sub["status"] == "succeeded":
                    continue  # 子流已成功，等同已完成步
                if sub["status"] == "paused":
                    self.resume_run(sub["id"])  # 父复活则暂停的子流一并续跑
                    break
                break  # running（等级联回调）或终态失败（父已被级联收口）
            t = latest.get(n)
            if t is None:
                if n in skipped:
                    continue  # D2：该步曾 when 跳过，重放时继续跳
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
                    self._finish_and_cascade(run_id, "succeeded")
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
        """立即中止：活跃任务全部发起取消，run 强制收口为 cancelled；成果留档可查。
        C1：递归中止活跃子 run（07——父终止=整树终止）。"""
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
        for sub in self._pipeline_repo.get_subruns(run_id).values():
            if sub["status"] in ("running", "paused"):
                try:
                    self.abort_run(sub["id"])  # 递归：子树整体终止
                except TaskConflictError:
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

    # 可批量重跑的状态：真失败态（paused 走「继续」/resume，不在此列）
    RERUNNABLE_STATUSES = ("failed", "failed_review", "cancelled", "interrupted")

    @staticmethod
    def _dedupe_by_file(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """同一文件只留**最新**一条（入参按 created_at 倒序）：防止「越重跑越多」。

        每次失败的重跑都会新产生一条 failed run，若不去重，下一次点「重跑失败项」会把
        历史失败与新失败一起重跑，数量指数增长（2026-09-14 用户反馈）。
        """
        seen: dict[str, dict[str, Any]] = {}
        for run in runs:
            key = str((run.get("input") or {}).get("file") or run.get("id"))
            seen.setdefault(key, run)
        return list(seen.values())

    def rerun_runs(self, run_ids: list[str]) -> dict[str, Any]:
        """批量重跑（批次失败项一键重跑）：逐条复用 rerun_run（原 run 留档、新 run 继承批次）。

        **同一文件只重跑最新一条**（其余记 skipped），单条失败不拖垮整批。
        """
        rerun: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        fetched: dict[str, dict[str, Any]] = {}
        for run_id in run_ids:
            run = self._pipeline_repo.get_run(run_id)
            if run is not None:
                fetched[run_id] = run
        ordered = sorted(fetched.values(), key=lambda r: str(r.get("created_at") or ""),
                         reverse=True)
        keep = {r["id"] for r in self._dedupe_by_file(ordered)}
        for run_id in run_ids:
            run = fetched.get(run_id)
            if run is None:
                skipped.append({"run_id": run_id, "reason": "任务不存在"})
                continue
            if str(run.get("status")) not in self.RERUNNABLE_STATUSES:
                skipped.append({"run_id": run_id,
                                "reason": f"状态不可重跑（{run.get('status')}）"})
                continue
            if run_id not in keep:
                skipped.append({"run_id": run_id, "reason": "同一文件已有更新的失败任务，已跳过"})
                continue
            try:
                created = self.rerun_run(run_id)
                rerun.append({"from": run_id, "to": created["run_id"]})
            except Exception as exc:  # noqa: BLE001 —— 单条失败不影响整批
                skipped.append({"run_id": run_id, "reason": f"{type(exc).__name__}: {exc}"})
        return {"count": len(rerun), "rerun": rerun, "skipped": skipped}

    def failed_runs_of_batch(self, batch_id: str, limit: int = 500) -> list[str]:
        """批次内可重跑的 run id：失败态（paused 走继续）且**同一文件只取最新一条**。"""
        runs = self._pipeline_repo.list_runs(batch_id=batch_id, limit=limit)
        failed = [r for r in runs if str(r.get("status")) in self.RERUNNABLE_STATUSES]
        return [r["id"] for r in self._dedupe_by_file(failed)]

    def best_runs_of_batch(self, batch_id: str) -> list[dict[str, Any]]:
        """批次内每个文件的最优 run（成功优先/同级最新）——**不受分页窗口限制**，批次导出用。"""
        return self._pipeline_repo.best_runs_by_batch(batch_id)

    def rerunnable_runs(self, batch_id: str | None = None, flow_ids: list[str] | None = None,
                        limit: int = 1000) -> dict[str, Any]:
        """可重跑清单（**全批次口径**，不受任务清单「只加载最新 N 条」限制）。

        判据 = 「**从未成功过**」且「最新一次是失败态」的文件：
        - 已成功过的文件即便后来某次重跑失败，也不需要再跑（交付物已在），否则计数会被
          历史失败的尝试虚高（2026-09-14 用户实测：界面 42，真实待处理 10）。
        - paused 不在内（那是「继续」的语义）。
        返回 {count, run_ids, files:[{file,name,run_id,status,error}], done_files:[已有成功译文的文件]}。
        """
        runs = self._pipeline_repo.list_runs(batch_id=batch_id, limit=limit)
        if flow_ids:
            wanted = set(flow_ids)
            runs = [r for r in runs if r.get("pipeline_id") in wanted]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for run in runs:  # created_at DESC（最新在前）
            key = str((run.get("input") or {}).get("file") or run["id"])
            grouped.setdefault(key, []).append(run)
        files: list[dict[str, Any]] = []
        done: list[str] = []
        for key, history in grouped.items():
            if any(r.get("status") == "succeeded" for r in history):
                done.append(key)   # 已有成功译文：前端据此把「重跑」置灰（与是否还有失败尝试无关）
                continue
            latest = history[0]
            if str(latest.get("status")) not in self.RERUNNABLE_STATUSES:
                continue
            files.append({
                "file": key, "name": Path(key).name, "run_id": latest["id"],
                "status": latest.get("status"), "error": (latest.get("error") or {}).get("message"),
            })
        return {"count": len(files), "run_ids": [f["run_id"] for f in files], "files": files,
                "done_files": done}

    def run_snapshot(self, run_id: str) -> dict[str, Any]:
        """steps 快照：每步最新任务 + 定义工具名（工作区/任务中心的考证视图）。"""
        run = self._pipeline_repo.get_run(run_id)
        if run is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        definition = self._pipeline_repo.get_definition(run["pipeline_id"])
        latest = self._pipeline_repo.latest_task_by_step(run_id)
        skipped = self._run_events.skipped_steps(run_id) if self._run_events else set()
        subruns = self._pipeline_repo.get_subruns(run_id)
        steps = []
        for n, step in enumerate(definition["steps"]):
            t = latest.get(n)
            entry: dict[str, Any] = {
                "step_index": n,
                "tool": step.get("tool"),
                "pipeline": step.get("pipeline"),
                "latest": t,
                "skipped": n in skipped,  # D2：when 跳步标记（审计留痕的可视化来源）
            }
            if "pipeline" in step and n in subruns:
                sub = subruns[n]  # C1：子流步展示子 run 状态（StepTrack 下钻入口）
                entry["subrun"] = {"run_id": sub["id"], "status": sub["status"],
                                   "pipeline_id": sub["pipeline_id"]}
            steps.append(entry)
        # Y2：详情直出 summary（进度含跳步、0 记录警示同列表口径）
        return {"run": run, "steps": steps, "summary": self._run_summary(run)}

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

    def list_runs(self, pipeline_id: str | None = None, limit: int = 50,
                  offset: int = 0, batch_id: str | None = None) -> dict[str, Any]:
        """job 粒度运行列表 + 每 run 摘要（产物/用量/统计）——翻译工作台任务区数据面。

        摘要走**批量轻投影**（3 条聚合查询覆盖整页），不再逐 run 拉整段 tasks 载荷。
        """
        runs = self._pipeline_repo.list_runs(pipeline_id=pipeline_id, limit=limit, offset=offset,
                                             batch_id=batch_id)
        for run in runs:
            run["summary"] = self._summaries([run])[run["id"]]
        return {"runs": runs, "total": self._pipeline_repo.count_runs(pipeline_id)}

    def _run_summary(self, run: dict[str, Any]) -> dict[str, Any]:
        """单 run 摘要（详情等单 run 场景用）。"""
        return self._summaries([run])[run["id"]]

    def _summaries(self, runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """批量摘要：状态/产物/用量一次取齐，逐 run 装配（契约与旧的逐 run 版一致）。"""
        run_ids = [r["id"] for r in runs]
        statuses = self._pipeline_repo.light_step_statuses(run_ids)
        outputs = self._pipeline_repo.light_step_outputs(run_ids)
        totals = self._pipeline_repo.steps_total_by_pipeline(
            [r.get("pipeline_id") or "" for r in runs])
        skipped: dict[str, list[dict[str, Any]]] = (
            self._run_events.skipped_steps_bulk(run_ids)
            if self._run_events is not None else {})
        titles: dict[str, dict[str, str]] = {
            d["id"]: {k: v.get("title") or k
                      for k, v in (d.get("input_schema") or {}).get("properties", {}).items()}
            for d in self._pipeline_repo.list_definitions()
        }
        # AB2：running 的 run 附最新工具进度消息（「已识别 12/42 页」），列表/浮窗直读
        progress_notes = (
            self._run_events.latest_progress_bulk(
                [r["id"] for r in runs if r.get("status") in ("running", "queued")])
            if self._run_events is not None else {})
        out: dict[str, dict[str, Any]] = {}
        for r in runs:
            summary = self._assemble_summary(
                statuses.get(r["id"], {}), outputs.get(r["id"], {}),
                totals.get(r.get("pipeline_id") or ""),
                skipped.get(r["id"], []),
                titles.get(r.get("pipeline_id") or ""))
            note = progress_notes.get(r["id"])
            if note:
                summary["latest_note"] = note
            out[r["id"]] = summary
        return out

    @staticmethod
    def _assemble_summary(step_statuses: dict[int, str], step_outputs: dict[int, dict[str, Any]],
                          steps_total: int | None,
                          skipped: list[dict[str, Any]] | None = None,
                          param_titles: dict[str, str] | None = None) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        translate: dict[str, Any] | None = None
        verify: dict[str, Any] | None = None
        for out in step_outputs.values():
            if not isinstance(out, dict):
                continue
            if out.get("path"):
                artifacts.append({"name": out.get("name"), "path": out.get("path")})
            if out.get("layered_file"):
                artifacts.append({"name": out.get("layered_name") or "可搜索.pdf",
                                  "path": out.get("layered_file")})
            if out.get("usage_by_model") is not None or out.get("usage") is not None:
                translate = out
            if out.get("statuses_len") is not None or out.get("review_count") is not None:
                verify = out
        summary: dict[str, Any] = {
            "artifacts": artifacts,
            "steps_total": steps_total,
            # Y1：when 跳过的步无 task 行，单独并入分母口径（2/3 误导的根因）
            "steps_done": sum(1 for s in step_statuses.values() if s in ("succeeded", "skipped"))
                          + len(skipped or []),
        }
        if translate is not None or verify is not None:
            counts = verify or translate or {}
            statuses_len = counts.get("statuses_len")
            review = counts.get("review_count")
            if review is None:
                review = (translate or {}).get("review_count") or 0
            summary.update({
                "usage": (translate or {}).get("usage"),
                "usage_by_model": (translate or {}).get("usage_by_model"),
                "calls": (translate or {}).get("calls"),
                "cache_hits": (translate or {}).get("cache_hits"),
                "review_count": review,
                "ok_count": max(statuses_len - review, 0) if statuses_len is not None else None,
            })
        # X4：识别部分页失败（未达熔断线时 run 落 succeeded）——列表要能看见并重试
        failed_pages = sum(o.get("failed_pages") or 0
                           for o in step_outputs.values() if isinstance(o, dict))
        if failed_pages:
            summary["failed_pages"] = failed_pages
        # AA3：勾稽/hook 告警数（校验不平、宽松修复等）——缺行/金额错一眼可见
        review_notes_counts = [o.get("review_notes_count") for o in step_outputs.values()
                               if isinstance(o, dict) and o.get("review_notes_count")]
        if review_notes_counts:
            summary["review_notes_count"] = sum(review_notes_counts)
        # Y4：识别完成但 0 记录——列表警示「成功但空库」
        records_counts = [o.get("records_count") for o in step_outputs.values()
                          if isinstance(o, dict) and o.get("records_count") is not None]
        if records_counts:
            summary["records_count"] = records_counts[-1]
        # Y2：跳步明细（人话原因）
        if skipped:
            summary["steps_skipped"] = [
                {"step_index": sk.get("step_index"),
                 "reason": PipelineService._skip_reason(sk.get("when") or {}, param_titles or {})}
                for sk in skipped]
        return summary

    @staticmethod
    def _skip_reason(when: dict[str, Any], titles: dict[str, str]) -> str:
        """把 when 条件翻译成人话（Y2）：input.export_units=True → 未开启：导出识别单元。"""
        parts: list[str] = []
        for key, expected in when.items():
            title = titles.get(key[6:]) if key.startswith("input.") else None
            name = title or key
            if expected == "@exists":
                parts.append(f"「{name}」无值（该步需要它）")
            elif expected is True:
                parts.append(f"未开启「{name}」")
            elif expected is False:
                parts.append(f"「{name}」需关闭")
            else:
                parts.append(f"「{name}」需为 {expected}")
        return "；".join(parts) or "条件未满足"

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

    def collect_run_artifacts(self, run_id: str, scope: str = "final") -> list[dict[str, Any]]:
        """收集某 run 的产物文件（供批量打包下载）。

        scope=final 只取**最后一步**的产物（用户要的成果）；all 取每一步（含中间临时产物）。
        判定方式：该步 output 里指向 data_dir 内**真实存在**的文件路径（`path`/`layered_file`/
        `render_file` … 任意键），排除 `*_name` 这类纯名称键。
        """
        if self._pipeline_repo.get_run(run_id) is None:
            raise TaskNotFoundError(f"管线运行不存在: {run_id}")
        outputs = self._pipeline_repo.outputs_by_step(run_id)
        if scope == "final" and outputs:
            outputs = {max(outputs): outputs[max(outputs)]}
        root = self._data_dir.resolve() if self._data_dir is not None else None
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for step in sorted(outputs):
            out = outputs[step]
            if not isinstance(out, dict):
                continue
            for key, value in out.items():
                if not isinstance(value, str) or not value or key.endswith("_name") or key == "name":
                    continue
                if Path(value).suffix.lower() not in ARTIFACT_SUFFIXES:
                    continue
                try:
                    candidate = Path(value)
                    if not candidate.is_absolute() or not candidate.is_file():
                        continue
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if root is not None and root not in resolved.parents:
                    continue
                if str(resolved) in seen:
                    continue
                seen.add(str(resolved))
                # 显示名：`xxx_file` 配 `xxx_name`（如 layered_file/layered_name），否则回落 output.name
                base = key[:-5] if key.endswith("_file") else key
                name = out.get(f"{base}_name") or out.get("name") or resolved.name
                found.append({"step": step, "key": key, "name": str(name),
                              "path": str(resolved), "size": resolved.stat().st_size})
        return found

    def run_artifact_usage(self, run_id: str) -> dict[str, int]:
        """单个 run（含子 run）的产物占用：`{files, bytes, dirs}`（只读，不删任何东西）。"""
        empty = {"files": 0, "bytes": 0, "dirs": 0}
        if self._data_dir is None:
            return empty
        root = (self._data_dir / "outputs").resolve()
        files = bytes_found = dirs = 0
        for rid in self._run_tree_ids(run_id):
            for task in self._task_repo.list_by_pipeline_run(rid):
                target = (root / str(task["handle"])).resolve()
                if root not in target.parents or not target.is_dir():
                    continue
                dirs += 1
                for path in target.rglob("*"):
                    if path.is_file():
                        files += 1
                        try:
                            bytes_found += path.stat().st_size
                        except OSError:
                            pass
        return {"files": files, "bytes": bytes_found, "dirs": dirs}

    def usage_report(self, run_ids: list[str] | None = None, pipeline_id: str | None = None,
                     limit: int = 50) -> dict[str, Any]:
        """产物占用报告（任务列表展示占用 / 清理前预演）：逐 run 明细 + 合计。"""
        if run_ids:
            targets = list(dict.fromkeys(str(r) for r in run_ids))
        else:
            targets = [r["id"] for r in self.list_runs(pipeline_id=pipeline_id, limit=limit)["runs"]]
        rows: list[dict[str, Any]] = []
        missing: list[str] = []
        total = {"files": 0, "bytes": 0, "dirs": 0}
        for run_id in targets:
            run = self._pipeline_repo.get_run(run_id)
            if run is None:
                missing.append(run_id)
                continue
            usage = self.run_artifact_usage(run_id)
            rows.append({"run_id": run_id, "pipeline_id": run["pipeline_id"], "status": run["status"],
                         "created_at": str(run.get("created_at") or ""), **usage})
            for key in total:
                total[key] += usage[key]
        return {"runs": rows, "total": total, "missing": missing}

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
