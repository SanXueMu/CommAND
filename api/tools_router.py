"""L3 工具路由：注册表查询与扫描注册。"""

from fastapi import APIRouter, HTTPException

import deps

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools() -> dict:
    return {"tools": deps.get_registry_service().list_tools()}


@router.get("/{tool_id}")
def get_tool(tool_id: str) -> dict:
    tool = deps.get_registry_service().get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool not found: {tool_id}")
    return tool


@router.post("/scan", status_code=202)
def scan_tools() -> dict:
    return deps.get_registry_service().scan()
