"""用户视图库 REST 端点（X5）：视图 tab 的「我的视图」数据面。

视图的三种来源：
- 内置视图：站点声明直发前端（不落库）；
- 模版携带视图：模版 detail.view_spec（挂模版走模版 CRUD）；
- **用户视图库（本 router）**：独立保存、跨模版复用，data/ocr/views/<id>.json。

同步 REST（轻量元数据 CRUD，无任务链路）——与模版管理 router 同构。
"""
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.errors import ToolDomainError, ToolNotFoundError
from store.ocr_view_store import ViewStore

router = APIRouter(prefix="/ocr/views", tags=["ocr-views"])


def _store() -> ViewStore:
    data_dir = os.environ.get("COMM_DATA_DIR") or None
    return ViewStore(data_dir) if data_dir else ViewStore()


class ViewUpsert(BaseModel):
    """视图新建/覆盖：id 缺省时由 name 生成 slug；同名（同 id）覆盖保留 created_at。"""

    id: str | None = None
    name: str
    spec: dict


@router.get("")
def list_views() -> dict:
    return {"views": _store().list()}


@router.get("/{view_id}")
def get_view(view_id: str) -> dict:
    try:
        return _store().get(view_id)
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
def upsert_view(body: ViewUpsert) -> dict:
    vid = body.id or _slugify(body.name)
    try:
        return _store().upsert({"id": vid, "name": body.name.strip(), "spec": body.spec})
    except ToolDomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{view_id}")
def delete_view(view_id: str) -> dict:
    try:
        return _store().delete(view_id)
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _slugify(name: str) -> str:
    """中文名直接落 slug 不可读也不合法——统一用 view.<hex> 形态，name 保留原文。"""
    import hashlib
    return "view." + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
