"""L3 管线路由：定义注册 / 列表 / 运行提交 / 运行详情。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import deps
from core.errors import TaskConflictError, TaskNotFoundError, ToolNotFoundError, ToolUserError

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class PipelineCreate(BaseModel):
    id: str
    name: str
    steps: list[dict[str, Any]] = Field(min_length=1)
    doc_md: str | None = None


class PipelineRunCreate(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


@router.post("", status_code=201)
def create_pipeline(body: PipelineCreate) -> dict:
    try:
        return deps.get_pipeline_service().register(body.id, body.name, body.steps, doc_md=body.doc_md)
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


@router.put("/{pipeline_id}", status_code=200)
def update_pipeline(pipeline_id: str, body: PipelineCreate) -> dict:
    if body.id != pipeline_id:
        raise HTTPException(status_code=422, detail="body.id 与路径 pipeline_id 不一致")
    try:
        return deps.get_pipeline_service().register(body.id, body.name, body.steps, doc_md=body.doc_md)
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{pipeline_id}")
def delete_pipeline(pipeline_id: str) -> dict:
    try:
        return deps.get_pipeline_service().delete(pipeline_id)
    except ToolUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{pipeline_id}/run", status_code=202)
def run_pipeline(pipeline_id: str, body: PipelineRunCreate) -> dict:
    try:
        return deps.get_pipeline_service().run(pipeline_id, body.input)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


runs_router = APIRouter(prefix="/pipeline-runs", tags=["pipelines"])


@runs_router.get("/{run_id}")
def get_pipeline_run(run_id: str) -> dict:
    service = deps.get_pipeline_service()
    try:
        tasks = service.get_run_tasks(run_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": deps.get_pipeline_repo().get_run(run_id), "tasks": tasks}


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
