"""L3 工具路由：注册表查询与扫描注册。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import deps

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolAvailability(BaseModel):
    """06 D1：工具启停/显隐（两键均可选，只动给出的键）。"""

    enabled: bool | None = None
    hidden: bool | None = None


@router.get("")
def list_tools() -> dict:
    return {"tools": deps.get_registry_service().list_tools()}


@router.get("/{tool_id}")
def get_tool(tool_id: str) -> dict:
    tool = deps.get_registry_service().get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_id}")
    return tool


@router.patch("/{tool_id}/availability")
def patch_tool_availability(tool_id: str, body: ToolAvailability) -> dict:
    """启停/显隐（06 D1）：disabled 不参与扫描发现但仍可查详情（注册校验用）。"""
    if body.enabled is None and body.hidden is None:
        raise HTTPException(status_code=422, detail="enabled/hidden 至少给一个")
    view = deps.get_tool_repo().set_availability(
        tool_id, enabled=body.enabled, hidden=body.hidden
    )
    if view is None:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_id}")
    return view


@router.post("/scan", status_code=202)
def scan_tools() -> dict:
    return deps.get_registry_service().scan()
