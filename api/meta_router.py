"""L3 元数据路由：协议级目录下发（状态机呈现语义由调度器侧定义）。

协议 v2（蓝图 03）：/meta/site 站点清单——会员向 CommWEB 声明视图集
（有哪些 Tab/页面/顺序/显隐/落地页），渲染控制权倒转给会员数据。
静态声明起步；when 条件由前端按握手探测结果求值。
"""

from fastapi import APIRouter

from core.status import STATUS_CATALOG

router = APIRouter(prefix="/meta", tags=["meta"])

SITE_MANIFEST: dict = {
    "site": {
        "name": "CommAND",
        "protocolVersion": "2",
        "views": [
            {
                "id": "tools",
                "type": "tools.grid",
                "title": "工具库",
                "icon": "appstore-outlined",
                "default": True,
                "props": {"defaultLayout": "card"},
            },
            {
                "id": "flows",
                "type": "flows.list",
                "title": "流",
                "icon": "node-index-outlined",
                "when": {"capability": "has_pipelines"},
            },
            {
                "id": "tasks",
                "type": "tasks.table",
                "title": "任务中心",
                "icon": "unordered-list-outlined",
            },
            {
                "id": "work",
                "type": "workspace.tabs",
                "title": "工作区",
                "icon": "desktop-outlined",
            },
        ],
    }
}


@router.get("/statuses")
def list_statuses() -> dict:
    return {"statuses": STATUS_CATALOG}


@router.get("/site")
def get_site() -> dict:
    return SITE_MANIFEST
