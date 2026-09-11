"""翻译域声明（Translee 工作台入口）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TRANSLATE_VIEW: dict = {
    "id": "translate",
    "type": "pipeline.studio",
    "title": "翻译工作台",
    "icon": "translation",
    "sort": 850,
    "props": {
        "flow_prefix": "flow.translate.",
        "description": (
            "Translee 全自动翻译：上传 xlsx 表格 / pdf 文档 / txt 文本，"
            "提取可译单元→批量翻译→保真质检→双语回填，产物可下载。"
        ),
        "empty_hint": "暂无翻译流——先运行 scripts/register_translee_flows.py 注册三条流。",
    },
}
