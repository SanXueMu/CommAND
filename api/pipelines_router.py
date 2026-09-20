"""L3 管线路由：定义注册 / 列表 / 运行提交 / 运行详情。"""

from typing import Any

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

import deps
from services import batch_manifest  # noqa: F401  (替换原件时同步批次清单)
from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class PipelineCreate(BaseModel):
    id: str
    name: str
    steps: list[dict[str, Any]] = Field(min_length=1)
    doc_md: str | None = None
    input_schema: dict[str, Any] | None = None  # 06：流级输入表单声明（FlowRunner 声明驱动）
    on_failure: dict[str, Any] | None = None    # 015：失败降级声明 {"fallback_flow": "<流 id>"}


class PipelineRunCreate(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    batch_id: str | None = None


class RunInputPatch(BaseModel):
    """就地修正任务参数（不含 file：换文件走 replace-file）。"""

    input: dict[str, Any] = Field(default_factory=dict)


class RerunBatchBody(BaseModel):
    """批次失败项一键重跑：给 run_ids 或 batch_id（给 batch 时取该批次内失败态 run）。"""

    run_ids: list[str] | None = None
    batch_id: str | None = None
    limit: int = Field(default=500, ge=1, le=2000)


@router.post("", status_code=201)
def create_pipeline(body: PipelineCreate) -> dict:
    try:
        return deps.get_pipeline_service().register(
            body.id, body.name, body.steps, doc_md=body.doc_md,
            input_schema=body.input_schema, on_failure=body.on_failure)
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_pipelines() -> dict:
    return {"pipelines": deps.get_pipeline_service().list()}


@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id: str) -> dict:
    try:
        return deps.get_pipeline_service().get(pipeline_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{pipeline_id}/stats")
def get_pipeline_stats(pipeline_id: str) -> dict:
    """量化性能：执行次数/成功率/平均耗时（按根管线归集）。"""
    try:
        deps.get_pipeline_service().get(pipeline_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return deps.get_task_repo().stats_by_pipeline(pipeline_id)


@router.put("/{pipeline_id}", status_code=200)
def update_pipeline(pipeline_id: str, body: PipelineCreate) -> dict:
    if body.id != pipeline_id:
        raise HTTPException(status_code=422, detail="body.id 与路径 pipeline_id 不一致")
    try:
        return deps.get_pipeline_service().register(
            body.id, body.name, body.steps, doc_md=body.doc_md,
            input_schema=body.input_schema, on_failure=body.on_failure)
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{pipeline_id}")
def delete_pipeline(pipeline_id: str) -> dict:
    try:
        return deps.get_pipeline_service().delete(pipeline_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{pipeline_id}/run", status_code=202)
def run_pipeline(pipeline_id: str, body: PipelineRunCreate) -> dict:
    try:
        return deps.get_pipeline_service().run(pipeline_id, body.input, batch_id=body.batch_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


runs_router = APIRouter(prefix="/pipeline-runs", tags=["pipelines"])


@runs_router.get("")
def list_runs(pipeline_id: str | None = None, limit: int = 50, offset: int = 0,
              batch_id: str | None = None) -> dict:
    """job 粒度运行列表（翻译工作台任务区）。pipeline_id / batch_id 缺省即全部。"""
    return deps.get_pipeline_service().list_runs(
        pipeline_id=pipeline_id, limit=limit, offset=offset, batch_id=batch_id)


class UsageQuery(BaseModel):
    """产物占用查询：给 run_ids 就逐个算，否则按 pipeline_id/limit 列最近任务。"""

    run_ids: list[str] | None = None
    pipeline_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


@runs_router.post("/usage")
def runs_usage(body: UsageQuery) -> dict:
    """任务产物占用报告（**只读**，不删任何东西）：任务列表展示占用 / 删除前预演将释放多少空间。"""
    return deps.get_pipeline_service().usage_report(
        run_ids=body.run_ids, pipeline_id=body.pipeline_id, limit=body.limit)


@runs_router.delete("/{run_id}")
def delete_run(run_id: str, purge_files: bool = True) -> dict:
    """删除任务。purge_files=true（默认）连带删除该任务全部产物目录（不可恢复）。"""
    try:
        return deps.get_pipeline_service().delete_run(run_id, purge_files=purge_files)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@runs_router.post("/{run_id}/replace-file", status_code=201)
async def replace_run_file(run_id: str, file: UploadFile) -> dict:
    """替换任务原件（旧版 .doc 另存为 .docx 后上传；或换一份正确的原件）。

    - 新文件落在**原文件同目录**（保持批次内相对位置），并**同步更新批次清单**（导出按清单还原）
    - 更新该 run 的 `input.file`，写审计事件 `file_replaced`
    - 仅允许非运行中的 run；替换后点「继续」（paused）或「重跑」即可
    """
    from api import files_router
    from services import batch_manifest

    service = deps.get_pipeline_service()
    run = deps.get_pipeline_repo().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {run_id}")
    if str(run.get("status")) in ("running", "queued"):
        raise HTTPException(status_code=409, detail="任务运行中，请先取消再替换原件")
    old_path = str((run.get("input") or {}).get("file") or "")
    if not old_path:
        raise HTTPException(status_code=422, detail="该任务没有原件路径，无法替换")
    try:
        rel = files_router._strict_rel(file.filename or "unnamed")  # noqa: SLF001
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target = Path(old_path).parent / rel.name
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
            size += len(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="上传的是空文件")

    new_input = dict(run.get("input") or {})
    new_input["file"] = str(target)
    deps.get_pipeline_repo().update_run_input(run_id, new_input)
    updated = batch_manifest.replace_file(
        deps.get_config().data_dir, str(run.get("batch_id") or ""), old_path,
        {"path": str(target), "name": target.name, "rel": target.name, "size": size})
    deps.get_run_event_repo().append(run_id, None, "file_replaced",
                                     detail={"old": old_path, "new": str(target),
                                             "manifest_updated": updated})
    return {"run_id": run_id, "file": str(target), "replaced": old_path,
            "size": size, "manifest_updated": updated}


@runs_router.patch("/{run_id}/input")
def patch_run_input(run_id: str, body: RunInputPatch) -> dict:
    """就地修正任务参数（密钥名/模型/术语等）后「继续」或「重跑」；file 请用 replace-file。"""
    if "file" in body.input:
        raise HTTPException(status_code=422, detail="换文件请用「替换原件」")
    repo = deps.get_pipeline_repo()
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {run_id}")
    if str(run.get("status")) in ("running", "queued"):
        raise HTTPException(status_code=409, detail="任务运行中，请先取消再修改参数")
    merged = {**(run.get("input") or {}), **body.input}
    repo.update_run_input(run_id, merged)
    deps.get_run_event_repo().append(run_id, None, "input_updated",
                                     detail={"keys": sorted(body.input)})
    return {"run_id": run_id, "input": merged}


@runs_router.get("/rerunnable")
def rerunnable_runs(batch_id: str | None = None, flow_ids: str | None = None,
                    limit: int = 1000) -> dict:
    """可重跑清单（全批次口径）：**从未成功过**且最新一次失败的文件。

    任务清单只加载最新 N 条 run，界面上的「失败项」计数会被历史失败的尝试虚高；
    这里按整个批次聚合，给出真实待处理清单（含对应 run_id 供一键重跑）。
    """
    flows = [f.strip() for f in (flow_ids or "").split(",") if f.strip()]
    return deps.get_pipeline_service().rerunnable_runs(
        batch_id=batch_id, flow_ids=flows or None, limit=limit)


@runs_router.get("/{run_id}")
def get_pipeline_run(run_id: str) -> dict:
    service = deps.get_pipeline_service()
    try:
        tasks = service.get_run_tasks(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # AF4：产物失效标记——任务输出里指向的产物文件已不在盘上（被删/被清理）时列出，
    # 前端产物区显示「已删除」徽标，避免点了下载才 404。
    data_dir = Path(deps.get_config().data_dir).resolve()
    missing: list[str] = []
    for task in tasks:
        out = task.get("output")
        if not isinstance(out, dict):
            continue
        for key, value in out.items():
            if (not isinstance(value, str) or not value
                    or key.endswith("_name") or key == "name"):
                continue
            if Path(value).suffix.lower() not in {
                    ".pdf", ".docx", ".xlsx", ".txt", ".md", ".csv", ".json",
                    ".pptx", ".xls", ".doc", ".zip", ".html", ".png", ".jpg", ".jpeg",
                    ".db"}:
                continue
            try:
                resolved = Path(value).resolve()
            except OSError:
                continue
            if data_dir in resolved.parents and not resolved.exists():
                missing.append(value)
    return {"run": deps.get_pipeline_repo().get_run(run_id), "tasks": tasks,
            "missing_artifacts": sorted(set(missing))}


@runs_router.post("/rerun-batch", status_code=202)
def rerun_batch(body: RerunBatchBody) -> dict:
    """批量重跑失败项（批次一键重跑）：逐条 rerun（原 run 留档、新 run 继承 batch_id）。

    paused 不在重跑范围（那是「继续」resume 的语义）；单条失败只记进 skipped。
    """
    service = deps.get_pipeline_service()
    run_ids = list(body.run_ids or [])
    if not run_ids and body.batch_id:
        run_ids = service.failed_runs_of_batch(body.batch_id, limit=body.limit)
    if not run_ids:
        return {"count": 0, "rerun": [], "skipped": []}
    return service.rerun_runs(run_ids[: body.limit])


@runs_router.post("/{run_id}/rerun", status_code=202)
def rerun_run(run_id: str, body: PipelineRunCreate | None = None) -> dict:
    """C4 重跑流：原 run 留档，以 run.input+覆盖起全新 run（06 四.1）。"""
    try:
        return deps.get_pipeline_service().rerun_run(
            run_id, input_override=body.input if body else None)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ToolUserError, ToolNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@runs_router.post("/{run_id}/pause")
def pause_run(run_id: str) -> dict:
    try:
        return deps.get_pipeline_service().pause_run(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@runs_router.post("/{run_id}/resume")
def resume_run(run_id: str) -> dict:
    try:
        return deps.get_pipeline_service().resume_run(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@runs_router.post("/{run_id}/abort")
def abort_run(run_id: str) -> dict:
    try:
        return deps.get_pipeline_service().abort_run(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@runs_router.post("/{run_id}/steps/{step_index}/abort")
def abort_step(run_id: str, step_index: int) -> dict:
    try:
        return deps.get_pipeline_service().abort_step(run_id, step_index)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class StepRerun(BaseModel):
    override: dict[str, Any] | None = None


@runs_router.post("/{run_id}/steps/{step_index}/rerun")
def rerun_step(run_id: str, step_index: int, body: StepRerun | None = None) -> dict:
    try:
        return deps.get_pipeline_service().rerun_step(
            run_id, step_index, override=(body.override if body else None))
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@runs_router.get("/{run_id}/snapshot")
def run_snapshot(run_id: str) -> dict:
    try:
        return deps.get_pipeline_service().run_snapshot(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@runs_router.get("/{run_id}/events")
def list_run_events(run_id: str, limit: int = 200) -> dict:
    try:
        return {"events": deps.get_pipeline_service().list_run_events(run_id, limit)}
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
