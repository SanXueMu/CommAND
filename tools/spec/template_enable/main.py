"""识别模版启停（spec.template.enable，E1）。"""
from command_shared.ocr_templates import TemplateStore


def run(input: dict, ctx, emit) -> dict:
    return TemplateStore().set_enabled(input["id"], bool(input["enabled"]))
