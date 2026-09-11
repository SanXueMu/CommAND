"""OCR 工作台声明：一站式识别体验，业务配置全 props 下发。"""

    # ---- OCR 工作台（还原 CommOCR 一站式体验：选模版→传文件→识别→结果导出；
    # 业务配置全部 props 下发，CommWEB 零业务内容） ----
# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
OCR_VIEW: dict = {
        "id": "ocr", "type": "ocr.studio", "title": "OCR 工作台",
        "icon": "scan-outlined", "sort": 50,
        "when": {"capability": "has_pipelines"},
        "props": {
            "description": "一站式识别工作台：选择识别模版，上传图片或 PDF，识别后查看结果并导出。",
            "recognizeFlow": "flow.ocr.smart",
            "exportFlow": "flow.ocrdb.view",
            "genFlow": "flow.specgen.img",
            "templatesPath": "/ocr/templates",
            "recordsPath": "/ocr/records",
            # 视图预览区：内置视图快选（records.view.query 按 name 匹配 ocr_views 内置库）
            "builtinViews": ["发票凭证视图", "合同清单视图", "审批签单视图", "合同关键词视图", "决算审定表视图"],
        },
    }
