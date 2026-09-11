"""OCR 工作台声明：一站式识别体验，业务配置全 props 下发。"""

from command_shared.ocr_views import BUILTIN_VIEWS

# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。


def _builtin_views() -> list[dict]:
    """内置视图快选：直接引用 ocr_views.BUILTIN_VIEWS，下发「名 → 完整 ViewSpec」。

    前端点选即把完整 spec 填入编辑器，records.view.query 零改动即可跑通
    （此前只下发视图名字符串，工具侧 ViewSpec(**str) 必抛 TypeError）。
    业务 spec 只存在于声明数据里（纯壳准则），CommWEB 代码零业务内容。
    形状取数组而非映射：保序（快选 Tag 排列是产品语义）+ 一份数据供展示与寻址。
    """
    return [
        {
            "id": item["id"],
            # spec.name 是干净中文名；item["name"] 带「（内置）」后缀，仅作兜底
            "name": item["spec"].get("name") or item["name"],
            "spec": item["spec"],
        }
        for item in BUILTIN_VIEWS
    ]


# OCR 工作台（还原 CommOCR 一站式体验：选模版→传文件→识别→结果导出；
# 业务配置全部 props 下发，CommWEB 零业务内容）
OCR_VIEW: dict = {
    "id": "ocr",
    "type": "ocr.studio",
    "title": "OCR 工作台",
    "icon": "scan-outlined",
    "sort": 50,
    "when": {"capability": "has_pipelines"},
    "props": {
        "description": "一站式识别工作台：选择识别模版，上传图片或 PDF，识别后查看结果并导出。",
        "recognizeFlow": "flow.ocr.smart",
        "exportFlow": "flow.ocrdb.view",
        "genFlow": "flow.specgen.img",
        # 视图预览区：内置视图快选（名 → 完整 ViewSpec，点选即用）
        "viewTool": "records.view.query",
        "templatesPath": "/ocr/templates",
        "recordsPath": "/ocr/records",
        "dbsPath": "/ocr/records/dbs",
        "builtinViews": _builtin_views(),
    },
}
