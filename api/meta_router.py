"""L3 元数据路由：协议级目录下发（状态机呈现语义由调度器侧定义）。

协议 v2（蓝图 03）：/meta/site 站点清单——会员向 CommWEB 声明视图集
（有哪些 Tab/页面/顺序/显隐/落地页），渲染控制权倒转给会员数据。
声明存 site_views 表（纯壳准则：声明是数据不是代码），启动 lifespan
幂等 seed 内置声明；when 条件由前端按握手探测结果求值。
"""

from fastapi import APIRouter

import deps
from core.status import STATUS_CATALOG

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/statuses")
def list_statuses() -> dict:
    return {"statuses": STATUS_CATALOG}


@router.get("/tool-categories")
def list_tool_categories() -> dict:
    from core.tool_categories import CATEGORIES

    return {"categories": CATEGORIES}


@router.get("/site")
def get_site() -> dict:
    views = [
        {k: v for k, v in view.items() if v is not None and k not in ("sort",)}
        for view in deps.get_site_repo().list()
    ]
    return {
        "site": {
            "name": "CommAND",
            "protocolVersion": "2",
            "views": views,
        }
    }
