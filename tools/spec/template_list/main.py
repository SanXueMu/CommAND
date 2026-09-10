"""识别模版列表（spec.template.list，E1）。"""
from command_shared.ocr_templates import TemplateStore


def run(input: dict, ctx, emit) -> dict:
    items = TemplateStore().list(
        enabled=input.get("enabled"), category=input.get("category"),
        keyword=input.get("keyword"))
    return {"templates": items, "total": len(items)}
