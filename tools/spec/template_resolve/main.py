"""识别模版解析（spec.template.resolve，E2）：渲染提示词 + 输出 vl.extract 直驱全量。"""
from command_shared.ocr_templates import TemplateStore, render_prompt
from core.errors import ToolDomainError


def run(input: dict, ctx, emit) -> dict:
    tpl = TemplateStore().get(input["id"])
    if not tpl.get("enabled", True):
        raise ToolDomainError(f"识别模版已停用: {input['id']}")
    fields = tpl.get("fields") or []
    return {
        "id": tpl["id"],
        "category": tpl.get("category"),
        "prompt": render_prompt(tpl["prompt_template"], fields,
                                tpl.get("rules"), tpl.get("example")),
        "fields": fields,
        "hooks": tpl.get("hooks") or [],
        "record_mode": tpl.get("record_mode"),
        "lenient": bool(tpl.get("lenient")),
        "view_spec": tpl.get("view_spec"),  # I/J：视图定义透传（全链导出步直读）
        "input_schema": tpl.get("input_schema"),  # I2：模版增量输入声明（级联表单数据源）
    }
