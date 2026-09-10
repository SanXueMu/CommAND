"""L3 管线路由：定义注册 / 列表 / 运行提交 / 运行详情。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import deps
from core.errors import TaskNotFoundError, ToolNotFoundError, ToolUserError

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
