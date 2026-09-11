"""内置站点声明（seed 数据源）——视图声明已目录化至 store/site_views/。

本文件保留为兼容薄壳：既有引用（main.py / tests）从此处导入
BUILTIN_SITE_VIEWS。新增/调整页面声明请改 store/site_views/ 下对应域文件。
"""

from __future__ import annotations

from store.site_views import BUILTIN_SITE_VIEWS

__all__ = ["BUILTIN_SITE_VIEWS"]
