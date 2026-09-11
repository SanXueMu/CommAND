"""工具分类目录：总类 → 子类 两级标签体系（子类 = 工具域中文名）。

单一事实源：tool id 首段（域）→ (总类, 子类) 映射。tool_repo 列表/详情
按此补 category/subcategory；/meta/tool-categories 下发目录给前端两级筛选。
"""

from __future__ import annotations

# 域 → (总类, 子类中文名)。新域接入时在此登记，前端零改动。
DOMAIN_CATEGORY: dict[str, tuple[str, str]] = {
    "pdf": ("文档处理", "PDF"),
    "docx": ("文档处理", "Word"),
    "txt": ("文档处理", "纯文本"),
    "table": ("文档处理", "表格"),
    "layout": ("文档处理", "版面"),
    "xlsx": ("文档处理", "Excel"),
    "img": ("图像影像", "图像"),
    "ocrdb": ("识别与结果", "识别结果库"),
    "records": ("识别与结果", "记录"),
    "spec": ("模板引擎", "模板"),
    "text": ("翻译文本", "文本"),
    "dev": ("开发调试", "开发"),
}

# 有序总类目录（前端两级筛选的渲染顺序）
CATEGORIES: list[dict[str, object]] = []
for _domain, (_cat, _sub) in DOMAIN_CATEGORY.items():
    _entry = next((e for e in CATEGORIES if e["name"] == _cat), None)
    if _entry is None:
        _entry = {"name": _cat, "subs": []}
        CATEGORIES.append(_entry)
    if _sub not in _entry["subs"]:  # type: ignore[typeddict-item]
        _entry["subs"].append(_sub)  # type: ignore[union-attr]


def category_of(tool_id: str) -> tuple[str, str] | None:
    """tool id 首段（域）→ (总类, 子类)；未登记域返回 None（前端归「未分类」）。"""
    domain = tool_id.split(".", 1)[0]
    return DOMAIN_CATEGORY.get(domain)
