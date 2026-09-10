"""识别模版管理 REST 端点（批 J1）：一站式管理界面 + 级联表单的数据面。

工具（spec.template.*）走异步任务链路，适合编排进流；
本 router 提供同步 REST，供管理界面 CRUD 与 CommWEB 表单级联直读。
"""
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from command_shared.ocr_templates import TemplateStore
from core.errors import ToolDomainError

router = APIRouter(prefix="/ocr/templates", tags=["ocr-templates"])


def _store() -> TemplateStore:
    data_dir = os.environ.get("COMM_DATA_DIR") or None
    return TemplateStore(data_dir) if data_dir else TemplateStore()


class TemplateUpsert(BaseModel):
    """模版新建/覆盖（全量主体，语义与 spec.template.upsert 一致）。"""

    template: dict


class TemplateEnabled(BaseModel):
    enabled: bool


@router.get("")
def list_templates(enabled: bool | None = None, category: str | None = None,
                   keyword: str | None = None) -> dict:
    return {"templates": _store().list(enabled=enabled, category=category, keyword=keyword)}


@router.get("/{template_id}")
def get_template(template_id: str) -> dict:
    tpl = _store().get(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"template not found: {template_id}")
    return tpl


@router.post("", status_code=201)
def upsert_template(body: TemplateUpsert) -> dict:
    try:
        return _store().upsert(body.template)
    except ToolDomainError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch("/{template_id}/enabled")
def set_enabled(template_id: str, body: TemplateEnabled) -> dict:
    try:
        return _store().set_enabled(template_id, body.enabled)
    except ToolDomainError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{template_id}")
def delete_template(template_id: str) -> dict:
    try:
        return _store().delete(template_id)
    except ToolDomainError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
