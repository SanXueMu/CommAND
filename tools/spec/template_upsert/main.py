"""识别模版保存（spec.template.upsert，E1）。"""
from command_shared.ocr_templates import TemplateStore


def run(input: dict, ctx, emit) -> dict:
    return TemplateStore().upsert(dict(input))
