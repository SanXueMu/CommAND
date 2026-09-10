"""L5 状态目录：任务与 run 状态的呈现语义（label/分组/终态性）单一事实源。

CommWEB 按此目录驱动渲染（StatusBadge / 分组筛选），调度器加状态只改这里。
分组语义：active(进行中) / succeeded(成功) / failed(失败) / cancelled(已取消)。
"""

STATUS_CATALOG: list[dict] = [
    {"value": "queued", "label": "排队中", "group": "active", "terminal": False},
    {"value": "running", "label": "运行中", "group": "active", "terminal": False},
    {"value": "paused", "label": "已暂停", "group": "active", "terminal": False},
    {"value": "succeeded", "label": "成功", "group": "succeeded", "terminal": True},
    {"value": "failed", "label": "失败", "group": "failed", "terminal": True},
    {"value": "failed_review", "label": "待复核", "group": "failed", "terminal": True},
    {"value": "cancelled", "label": "已取消", "group": "cancelled", "terminal": True},
    {"value": "interrupted", "label": "已中断", "group": "cancelled", "terminal": True},
]
