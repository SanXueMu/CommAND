"""流域声明：侧栏筛选 + 行列表（v3 槽位试点首个域）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
FLOWS_VIEW: dict = {
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
    }
