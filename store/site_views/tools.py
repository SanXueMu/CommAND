"""工具库域声明：两级筛选侧栏 + 卡片列表。"""

    # ---- 协议级通用视图（任何会员都有） ----
# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TOOLS_VIEW: dict = {
        "id": "tools", "type": "tools.grid", "title": "工具库",
        "icon": "appstore-outlined", "default": True, "sort": 10,
        # 协议 v3 槽位声明：两级筛选侧栏 + 卡片列表；detail 弹窗/详情路由为前端内置语义。
        "props": {
            "defaultLayout": "card",
            "slots": {
                "sidebar": {"template": "sidebar.filter", "props": {"width": 200}},
                "list": {
                    "template": "list.panel",
                    "props": {
                        "layout": "card", "renderer": "tool-card",
                        "searchPlaceholder": "搜索工具（id/名称/描述/标签）", "emptyText": "没有符合条件的工具",
                        "pagination": {"pageSize": 12},
                    },
                },
            },
        },
    }
