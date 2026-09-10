"""三件套转模版（spec.template.from_spec，E3）：specgen 产出入库为识别模版。"""
from command_shared.ocr_templates import TemplateStore
from core.errors import ToolDomainError


def run(input: dict, ctx, emit) -> dict:
    spec = input.get("task_spec") or {}
    template = spec.get("template")
    if not isinstance(template, str) or not template:
        raise ToolDomainError("task_spec.template 须为非空字符串")
    prompt_template = template
    if "{fields}" not in prompt_template:
        prompt_template = f"{prompt_template}\n\n请识别以下字段：{{fields}}"
    return TemplateStore().upsert({
        "id": input["id"], "name": input["name"], "category": input["category"],
        "prompt_template": prompt_template,
        "fields": spec.get("fields"),
        "rules": spec.get("rules"),
        "example": spec.get("example"),
        "hooks": input.get("postprocess") or [],
        "record_mode": spec.get("record_mode"),
        "lenient": bool(spec.get("lenient")),
        "view_spec": input.get("view_spec") or {},
    })
