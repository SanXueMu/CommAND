"""识别模版删除（spec.template.delete，E1）。"""
from command_shared.ocr_templates import TemplateStore


def run(input: dict, ctx, emit) -> dict:
    return TemplateStore().delete(input["id"])
