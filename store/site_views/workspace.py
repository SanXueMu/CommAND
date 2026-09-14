"""工作区域声明（多标签执行容器）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
WORKSPACE_VIEW: dict = {
        "id": "work", "type": "workspace.tabs", "title": "工作区",
        "icon": "desktop-outlined", "sort": 40,
        # 页眉渲染（props.nav，向后兼容字段）：菜单父项——点击出下拉，首项「默认」= 本视图自身，
        # 其后为 nav.kind=child 且 group=work 的子视图（OCR 工作台 / 翻译工作台）。
        "props": {
            "nav": {"kind": "menu"},
            "defaultLabel": "默认",
        },
    }
