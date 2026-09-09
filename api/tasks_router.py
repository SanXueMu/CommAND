"""L3 任务路由：提交（信封校验）/ 查询 / 列表 / 取消；SSE 事件流于 S2b。"""

from fastapi import APIRouter, HTTPException, Query

import deps
from api.schemas import TaskCreate
from core.errors import (
    TaskConflictError,
    TaskNotFoundError,
    ToolNotFoundError,
    ToolUserError,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=202)
def create_task(body: TaskCreate) -> dict:
    try:
        return deps.get_dispatch_service().submit(body.tool, body.input)
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolUserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def list_tasks(
    status: str | None = Query(default=None), limit: int = Query(default=50, le=200)
) -> dict:
    return {"tasks": deps.get_dispatch_service().list(status=status, limit=limit)}


@router.get("/{handle}")
def get_task(handle: str) -> dict:
    try:
        return deps.get_dispatch_service().get(handle)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{handle}/cancel")
def cancel_task(handle: str) -> dict:
    try:
        return deps.get_dispatch_service().cancel(handle)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
