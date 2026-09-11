"""任务中心域声明：归类侧栏 + 行列表。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TASKS_VIEW: dict = {
        "id": "tasks", "type": "tasks.table", "title": "任务中心",
        "icon": "unordered-list-outlined", "sort": 30,
        # 协议 v3 槽位声明：归类侧栏 + 行列表；detail 弹窗为前端内置语义动作。
        "props": {
            "slots": {
                "sidebar": {"template": "sidebar.filter", "props": {"width": 128}},
                "list": {
                    "template": "list.panel",
                    "props": {
                        "layout": "row", "renderer": "task-row",
                        "searchPlaceholder": "搜索任务",
                        "pagination": {"pageSize": 20},
                    },
                },
            },
        },
    }
