"""任务状态目录：单一事实源（调度器所有），前端分组/徽章由此驱动。

group 取值：active / succeeded / failed / cancelled（前端色板按组映射）。
"""

STATUS_CATALOG: list[dict[str, object]] = [
    {"value": "queued", "label": "排队中", "group": "active", "terminal": False},
    {"value": "running", "label": "运行中", "group": "active", "terminal": False},
    {"value": "succeeded", "label": "成功", "group": "succeeded", "terminal": True},
    {"value": "failed", "label": "失败", "group": "failed", "terminal": True},
    {"value": "failed_review", "label": "待复核", "group": "failed", "terminal": True},
    {"value": "cancelled", "label": "已取消", "group": "cancelled", "terminal": True},
    {"value": "interrupted", "label": "已中断", "group": "cancelled", "terminal": True},
]
