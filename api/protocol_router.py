"""协议控制面路由（蓝图「飞升」）：

- GET  /meta/protocol                    —— 会员协议声明（CommWEB 探测协商用）
- GET  /control/protocol/releases        —— 协议发布历史（只追加）
- GET  /control/protocol/providers/{pid}/state —— 映像/投影/同步状态总览
- POST /control/protocol/providers/{pid}/capture —— 刷新会员映像（访问会员重新采集）
- POST /control/protocol/providers/{pid}/sync    —— 同步当前协议（仅用 PG 历史映像，会员离线可执行）
"""

from fastapi import APIRouter, HTTPException

import deps

router = APIRouter(prefix="/control/protocol", tags=["protocol"])

DEFAULT_PROVIDER = "default"


@router.get("/releases")
def list_releases() -> dict:
    return {"releases": deps.get_protocol_repo().list_releases()}


@router.get("/providers/{provider_id}/state")
def provider_state(provider_id: str) -> dict:
    return deps.get_protocol_sync_service().state(provider_id)


@router.post("/providers/{provider_id}/capture")
def capture(provider_id: str) -> dict:
    try:
        return deps.get_protocol_sync_service().capture(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/providers/{provider_id}/sync")
def sync(provider_id: str, to_release_id: int | None = None) -> dict:
    try:
        return deps.get_protocol_sync_service().sync(provider_id, to_release_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
