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
        # 协议 v3 槽位声明（试点）：侧栏筛选 + 列表模板；detail 弹窗为前端内置语义动作。
        "props": {
            "slots": {
                "sidebar": {"template": "sidebar.filter", "props": {"width": 168}},
                "list": {
                    "template": "list.panel",
                    "props": {
                        "layout": "row", "renderer": "flow-row",
                        "searchPlaceholder": "搜索流（id/名称/步骤）", "emptyText": "暂无已注册的流",
                        "pagination": False,
                    },
                },
            },
        },
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
    # ---- OCR 工作台（还原 CommOCR 一站式体验：选模版→传文件→识别→结果导出；
    # 业务配置全部 props 下发，CommWEB 零业务内容） ----
    {
        "id": "ocr", "type": "ocr.studio", "title": "OCR 工作台",
        "icon": "scan-outlined", "sort": 50,
        "when": {"capability": "has_pipelines"},
        "props": {
            "description": "一站式识别工作台：选择识别模版，上传图片或 PDF，识别后查看结果并导出。",
            "recognizeFlow": "flow.ocr.smart",
            "exportFlow": "flow.ocrdb.view",
            "genFlow": "flow.specgen.img",
            "templatesPath": "/ocr/templates",
            "recordsPath": "/ocr/records",
        },
    },
    # ---- 模版管理（批 J1 一站式；OCR 子功能按三级概念归流库，不再占导航 Tab） ----
    {
        "id": "templates", "type": "templates.manager", "title": "模版管理",
        "icon": "database-outlined", "sort": 500,
        "props": {"description": "识别规则模版一站式管理：列表 / 启停 / 删除 / 新建覆盖。"},
    },
]
