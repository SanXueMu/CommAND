"""翻译域 REST 端点（translee 体验还原，T1/T2）。

- /translate/templates：翻译模版（语言对 + 术语表 + 模型）CRUD（供工作台侧栏与模板管理）
- /translate/dict：已译字典浏览（dict_cache 全局库，模糊检索 + 状态/模型筛选 + 分页）

与 ocr_templates_router 同款取舍：工具链路走异步任务，本 router 供工作台直读。
"""
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from command_shared import dict_cache
from command_shared.translate_templates import TranslateTemplateStore
from core.errors import ToolDomainError, ToolNotFoundError

router = APIRouter(prefix="/translate", tags=["translate"])


def _store() -> TranslateTemplateStore:
    return TranslateTemplateStore(os.environ.get("COMMAND_DATA_DIR") or None)


class TemplateUpsert(BaseModel):
    template: dict


class TemplateEnabled(BaseModel):
    enabled: bool


@router.get("/templates")
def list_templates(enabled: bool | None = None, keyword: str | None = None) -> dict:
    return {"templates": _store().list(enabled=enabled, keyword=keyword)}


@router.get("/templates/{template_id}")
def get_template(template_id: str) -> dict:
    try:
        return _store().get(template_id)
    except (ToolDomainError, ToolNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/templates", status_code=201)
def upsert_template(body: TemplateUpsert) -> dict:
    try:
        return _store().upsert(body.template)
    except ToolDomainError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch("/templates/{template_id}/enabled")
def set_enabled(template_id: str, body: TemplateEnabled) -> dict:
    try:
        return _store().set_enabled(template_id, body.enabled)
    except (ToolDomainError, ToolNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/templates/{template_id}")
def delete_template(template_id: str) -> dict:
    try:
        return _store().delete(template_id)
    except (ToolDomainError, ToolNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/dict")
def browse_dict(q: str | None = None, status: str | None = None, model: str | None = None,
                limit: int = 50, offset: int = 0) -> dict:
    """已译字典浏览（全局共享字典库）。"""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conn = dict_cache.open_dict()
    try:
        return dict_cache.browse(conn, q=q, status=status, model=model, limit=limit, offset=offset)
    finally:
        conn.close()
