"""设置域声明（会员密钥管理入口）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
SETTINGS_VIEW: dict = {
        "id": "settings", "type": "settings.keys", "title": "设置",
        "icon": "api-outlined", "sort": 900,
        # 不进主导航：作为页眉右侧「设置」下拉的功能项（order 小的在前）
        "props": {"nav": {"kind": "header", "label": "APIKey管理", "order": 20}},
    }
