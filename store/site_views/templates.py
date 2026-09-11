"""模版管理域声明：一站式 CRUD（批 J1）。"""

    # ---- 模版管理（批 J1 一站式；OCR 子功能按三级概念归流库，不再占导航 Tab） ----
# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TEMPLATES_VIEW: dict = {
        "id": "templates", "type": "templates.manager", "title": "模版管理",
        "icon": "database-outlined", "sort": 500,
        "props": {"description": "识别规则模版一站式管理：列表 / 启停 / 删除 / 新建覆盖。"},
    }
