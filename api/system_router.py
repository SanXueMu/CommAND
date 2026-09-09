"""L3 系统路由：健康检查（PG 连通 / 版本）。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import deps

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> JSONResponse:
    db_ok = deps.get_db().ping()
    payload = {"status": "ok" if db_ok else "degraded", "db": db_ok, "version": "0.1.0"}
    if not db_ok:
        return JSONResponse(status_code=503, content=payload)
    return JSONResponse(content=payload)
