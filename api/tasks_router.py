"""L3 任务路由：提交（信封）/ 驱动 handle 生命周期（S2 实现入库与 SSE）。"""

from fastapi import APIRouter, HTTPException

from api.schemas import TaskCreate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=501)
def create_task(body: TaskCreate) -> dict:
    raise HTTPException(status_code=501, detail="任务提交将在 S2 实现（PG 队列 + dispatch_service）")


@router.get("", status_code=501)
def list_tasks() -> dict:
    raise HTTPException(status_code=501, detail="任务列表将在 S2 实现")


@router.get("/{handle}", status_code=501)
def get_task(handle: str) -> dict:
    raise HTTPException(status_code=501, detail=f"任务详情将在 S2 实现: {handle}")


@router.post("/{handle}/cancel", status_code=501)
def cancel_task(handle: str) -> dict:
    raise HTTPException(status_code=501, detail=f"协作取消将在 S2 实现: {handle}")


@router.get("/{handle}/events", status_code=501)
def task_events(handle: str) -> dict:
    raise HTTPException(status_code=501, detail=f"SSE 事件流将在 S2 实现: {handle}")
