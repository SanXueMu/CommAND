"""注册表路由（蓝图「飞升」§快速启动）：

- GET  /control/registration/template —— 下载《注册CommWeb.xlsx》模板（含下拉约束/说明/组件清单）
- POST /control/registration/preview  —— 上传填好的表格 → 校验 + 返回受限 migration JSON
- POST /control/registration/apply    —— 审核后导入（服务端重校验，只 upsite_views 不删）
"""

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response

import deps
from services.registration_service import build_template

router = APIRouter(prefix="/control/registration", tags=["registration"])


@router.get("/template")
def download_template() -> Response:
    data = build_template()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="RegisterCommWeb.xlsx"'},
    )


@router.post("/preview")
async def preview(file: UploadFile) -> dict:
    data = await file.read()
    try:
        return deps.get_registration_service().preview(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply")
async def apply(body: dict) -> dict:
    try:
        return deps.get_registration_service().apply(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
