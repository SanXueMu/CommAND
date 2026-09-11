"""L3 任务路由：提交（信封校验）/ 查询 / 列表 / 取消 / SSE 事件流。"""

import json
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

import deps
from api.schemas import TaskCreate
from core.errors import (
    TaskConflictError,
    TaskNotFoundError,
    ToolNotFoundError,
    ToolUserError,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

TERMINAL = {"succeeded", "failed", "failed_review", "cancelled", "interrupted"}


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
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, description="检索：工具中文名/任务号/流中文名"),
    kind: str | None = Query(default=None, description="归类筛选: tool/flow/workflow（06 C4）"),
) -> dict:
    try:
        return deps.get_dispatch_service().list(status=status, limit=limit, kind=kind, offset=offset, q=q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.get("/{handle}/events")
def task_events(handle: str) -> StreamingResponse:
    try:
        deps.get_dispatch_service().get(handle)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    event_repo = deps.get_event_repo()
    task_repo = deps.get_task_repo()

    def stream():
        after_id = 0
        idle = 0
        while idle < 60:
            events = event_repo.list_by_handle(handle, after_id=after_id)
            for event in events:
                after_id = event["id"]
                payload = json.dumps(
                    {"data": event["data"], "created_at": str(event["created_at"])},
                    ensure_ascii=False,
                )
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"
                idle = 0
            task = task_repo.get(handle)
            if task is not None and task["status"] in TERMINAL:
                done = json.dumps(
                    {"status": task["status"], "output": task["output"], "error": task["error"]},
                    ensure_ascii=False,
                    default=str,
                )
                yield f"event: done\ndata: {done}\n\n"
                return
            idle += 1
            yield ": keepalive\n\n"
            time.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")
