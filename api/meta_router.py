"""L3 元数据路由：协议级目录下发（状态机呈现语义由调度器侧定义）。"""

from fastapi import APIRouter

from core.status import STATUS_CATALOG

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/statuses")
def list_statuses() -> dict:
    return {"statuses": STATUS_CATALOG}
