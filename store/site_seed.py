"""内置站点声明（seed 数据源）。

纯壳准则：这些业务声明只允许存在于 CommAND（业务容器），以数据形式经
/meta/site 下发给 CommWEB；CommWEB 代码内零业务内容。启动 lifespan 幂等
seed 进 site_views 表——注册时与每次热部署后业务数据自动入 PG。
"""

from __future__ import annotations

BUILTIN_SITE_VIEWS: list[dict] = [
    # ---- 协议级通用视图（任何会员都有） ----
    {
        "id": "tools", "type": "tools.grid", "title": "工具库",
        "icon": "appstore-outlined", "default": True, "sort": 10,
        "props": {"defaultLayout": "card"},
    },
    {
        "id": "flows", "type": "flows.list", "title": "流",
        "icon": "node-index-outlined", "sort": 20,
        "when": {"capability": "has_pipelines"},
    },
    {
        "id": "tasks", "type": "tasks.table", "title": "任务中心",
        "icon": "unordered-list-outlined", "sort": 30,
    },
    {
        "id": "work", "type": "workspace.tabs", "title": "工作区",
        "icon": "desktop-outlined", "sort": 40,
    },
    {
        "id": "settings", "type": "settings.keys", "title": "设置",
        "icon": "api-outlined", "sort": 900,
    },
    # ---- OCR 业务声明（CommOCR 移植） ----
    {
        "id": "ocr-recognize", "type": "pipeline.studio", "title": "OCR 识别",
        "icon": "file-text-outlined", "sort": 100,
        "props": {
            "description": "模板流已固化字段/提示词/钩子；通用流参数全开放。",
            "flow_prefix": "flow.ocr.",
            "flow_exclude_prefixes": ["flow.ocrdb.", "flow.specgen."],
        },
    },
    {
        "id": "ocr-results", "type": "data.browser", "title": "OCR 结果",
        "icon": "database-outlined", "sort": 110,
        "when": {"capability": "has_files"},
        "props": {
            "source": {"kind": "dbs", "upload": True, "label": "OCR 结果库"},
            "extract": {
                "tool": "ocrdb.extract.units",
                "input": {"db": "{{source}}", "mode": "records"},
            },
        },
    },
    {
        "id": "ocr-views", "type": "data.browser", "title": "OCR 视图导出",
        "icon": "table-outlined", "sort": 120,
        "when": {"capability": "has_files"},
        "props": {
            "source": {"kind": "records_json", "label": "records 输入", "hint": "从「OCR 结果」页提取后粘贴，或直接粘贴 JSON 数组"},
            "view": {
                "tool": "records.view.query",
                "records_key": "records",
                "spec_label": "ViewSpec（内置视图名点选快选，或完整 JSON）",
                "builtin_views": [
                    "合同关键词视图", "发票待审视图", "决算勾稽视图", "项目概览视图", "审计痕迹视图",
                ],
            },
            "export": {
                "tool": "records.export.xlsx",
                "label": "导出 xlsx",
                "input": {
                    "columns": "{{view.columns}}",
                    "rows": "{{view.rows}}",
                    "splits": "{{view.splits}}",
                    "name": "视图导出",
                },
            },
        },
    },
    {
        "id": "ocr-specgen", "type": "pipeline.studio", "title": "OCR 模板生成",
        "icon": "bulb-outlined", "sort": 130,
        "when": {"capability": "has_files"},
        "props": {
            "description": "样例 + 需求描述 → 三件套（识别配置/钩子/视图），校验通过后可另存为识别管线。",
            "flow_ids": ["flow.specgen.pdf", "flow.specgen.img"],
            "scheme_field": {
                "key": "requirement",
                "label": "识别需求描述",
                "kind": "textarea",
                "placeholder": "例：识别决算审定表，需要字段：项目名称、送审金额、审定金额、审增审减率；金额千分位归一；勾稽不符标记待审。",
                "schemes": [
                    {"value": "flow.specgen.pdf", "label": "方案一：文本层 PDF → 纯语言 LLM"},
                    {"value": "flow.specgen.img", "label": "方案二：多模态直读"},
                ],
            },
            "save_as": {
                "button_label": "另存为识别管线",
                "pipeline_prefix": "flow.ocr.custom.",
                "pipeline_name_from_input": "requirement",
                "flow_prefix_filter": "flow.ocr.",
                "steps": [
                    {
                        "tool": "img.vl.extract",
                        "input": {
                            "file": "{{input.file}}",
                            "db": "{{input.db}}",
                            "key_name": "{{input.key_name}}",
                            "raw_prompt": True,
                            "prompt": "{{spec.task_spec.template}}",
                            "fields": "{{spec.task_spec.fields}}",
                            "rules": "{{spec.task_spec.rules}}",
                            "example": "{{spec.task_spec.example}}",
                            "record_mode": "{{spec.task_spec.record_mode}}",
                            "postprocess": "{{spec.postprocess}}",
                        },
                    }
                ],
            },
        },
    },
]
