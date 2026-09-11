"""翻译域声明（Translee 工作台入口）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TRANSLATE_VIEW: dict = {
    "id": "translate",
    "type": "translate.studio",
    "title": "翻译工作台",
    "icon": "translation-outlined",
    "sort": 850,
    "props": {
        "flow_prefix": "flow.translate.",
        # 文件后缀 → 翻译流（组件按扩展名路由，不在前端写死流 ID）
        "routes": [
            {"ext": [".xlsx", ".xls"], "flow": "flow.translate.xlsx"},
            {"ext": [".pdf"], "flow": "flow.translate.pdf"},
            {"ext": [".txt", ".md"], "flow": "flow.translate.txt"},
        ],
        "templatesPath": "/translate/templates",
        "dictPath": "/translate/dict",
        # 目标/源语言候选（值须为引擎可识别语言名）
        "languages": [
            {"value": "Chinese", "label": "中文"},
            {"value": "English", "label": "英文"},
            {"value": "Japanese", "label": "日文"},
            {"value": "Korean", "label": "韩文"},
        ],
        "description": (
            "Translee 全自动翻译：上传 xlsx 表格 / pdf 文档 / txt 文本 →"
            "提取可译单元 → 批量翻译 → 保真质检 → 双语回填，"
            "支持翻译模版（语言对/术语表/模型）与已译字典浏览。"
        ),
        "empty_hint": "暂无翻译流——先运行 scripts/register_translee_flows.py 注册三条流。",
    },
}
