"""L3 keys 路由：LLM 密钥命名管理（列表永远打码）。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import deps

router = APIRouter(prefix="/keys", tags=["keys"])


class KeyUpsert(BaseModel):
    """创建/更新密钥；is_default=true 时自动取消其他默认。"""

    name: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=32)
    base_url: str = ""
    api_key: str = Field(min_length=1)
    is_default: bool = False


@router.get("")
def list_keys() -> dict:
    return {"keys": deps.get_key_repo().list()}


@router.put("/{name}", status_code=200)
def upsert_key(name: str, body: KeyUpsert) -> dict:
    if body.name != name:
        raise HTTPException(status_code=422, detail="body.name 与路径 name 不一致")
    deps.get_key_repo().upsert(
        name=name,
        provider=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        is_default=body.is_default,
    )
    return {"name": name, "stored": True}


@router.delete("/{name}")
def delete_key(name: str) -> dict:
    if not deps.get_key_repo().delete(name):
        raise HTTPException(status_code=404, detail=f"key not found: {name}")
    return {"name": name, "deleted": True}
