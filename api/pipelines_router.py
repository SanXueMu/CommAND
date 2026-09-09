"""L3 管线路由：线性管线定义与运行（S3 实现）。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", status_code=501)
def list_pipelines() -> dict:
    raise HTTPException(status_code=501, detail="管线定义将在 S3 实现")


@router.post("", status_code=501)
def create_pipeline() -> dict:
    raise HTTPException(status_code=501, detail="管线创建将在 S3 实现")


@router.post("/{pipeline_id}/run", status_code=501)
def run_pipeline(pipeline_id: str) -> dict:
    raise HTTPException(status_code=501, detail=f"管线运行将在 S3 实现: {pipeline_id}")
