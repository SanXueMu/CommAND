"""翻译域声明（Translee 工作台入口）。"""


# 一域一文件（协议 v3：改本文件即改该页面声明，seed 时聚合下发）。
TRANSLATE_VIEW: dict = {
    "id": "translate",
    "type": "translate.studio",
    "title": "翻译工作台",
    "icon": "translation-outlined",
    "sort": 850,
    "props": {
        # 页眉渲染：归入「工作区」下拉（替换原先的独立 Tab）
        "nav": {"kind": "child", "group": "work", "label": "翻译工作台"},
        # PDF 处理口径（批量）：声明候选 + 说明，前端不写死；text 口径下扫描件会暂停等补文字层
        "pdfModes": [
            {"value": "auto", "label": "自动探测", "hint": "按 PDF 有无文字层自动选流：文字版走版式翻译，扫描件走图片翻译（保留版式，产物无文字层）"},
            {"value": "text", "label": "全部文字版", "hint": "一律走文字版链路（不使用 qwen-mt-image）；扫描件会暂停，提示先补文字层（如 ocrmypdf）"},
            {"value": "image", "label": "全部图片版", "hint": "一律走图片翻译（qwen-mt-image，0.004 元/张）；产物为图片版 PDF，无文字层"},
        ],
        "flow_prefix": "flow.translate.",
        # 文件后缀 → 翻译流（组件按扩展名路由，不在前端写死流 ID）；
        # 同后缀多条 = 用户可选处理方式（如 pdf 可版式翻译、双语 docx 或图片翻译）；
        # for: 供工作台按「系统探测」自动选流——text=有文字层, scanned=扫描件
        "routes": [
            {"ext": [".xlsx", ".xls"], "flow": "flow.translate.xlsx",
             "label": "表格翻译（每个原工作表后附「_翻译结果」工作表）"},
            {"ext": [".pdf"], "flow": "flow.translate.pdf.layout", "for": "text",
             "label": "版式翻译（原位覆盖 / 双语对照 PDF）"},
            {"ext": [".pdf"], "flow": "flow.translate.pdf", "label": "文字版 PDF → 双语 docx"},
            {"ext": [".pdf"], "flow": "flow.translate.pdf.image", "for": "scanned",
             "label": "图片版 PDF（扫描件 · 图片翻译，保留版式）"},
            {"ext": [".txt", ".md"], "flow": "flow.translate.txt", "label": "文本翻译（双语 docx）"},
            {"ext": [".docx"], "flow": "flow.translate.docx", "label": "Word 翻译（段落对照 / 原位覆盖 docx）"},
            # 旧版 .doc：可提交，子任务会**暂停**（不失败）等人工另存为 .docx 后续跑，源文件随批次导出
            {"ext": [".doc"], "flow": "flow.translate.docx",
             "label": "Word 翻译（旧版 .doc：任务将暂停，另存为 .docx 后继续）"},
            {"ext": [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"], "flow": "flow.translate.image",
             "label": "图片翻译（qwen-mt-image，保留排版）"},
            # PPT：本轮不翻译，但**生成一条暂停记录**留档（可见、可导出），原文件随批次导出
            {"ext": [".ppt", ".pptx"], "flow": "flow.translate.skip", "skip": True,
             "label": "PPT（暂不支持翻译：任务暂停留档，原文件随批次导出）"},
        ],
        # 不支持的后缀 → 组件给出明确提示（声明驱动，不写死在前端）；
        # .doc 已改为可提交（子任务暂停等另存为 .docx），故不在此列。
        "unsupported": [],
        # 通用附加参数（声明驱动；when_flow 指定仅该流显示）
        "params": [
            # 模型：可选可手写（CommWEB combo），默认取各流在 CommAND 中的成熟集成模型。
            # 文档链默认 qwen-mt-flash（专用翻译模型，实测 0.8s/10 条）；留空则用密钥默认。
            {"name": "model", "label": "翻译模型", "type": "combo", "default": "qwen-mt-flash",
             "when_flow": ["flow.translate.docx", "flow.translate.pdf", "flow.translate.pdf.layout",
                           "flow.translate.txt", "flow.translate.xlsx"],
             "options": [
                 {"value": "qwen-mt-flash", "label": "qwen-mt-flash（专用翻译，默认）"},
                 {"value": "qwen3.7-flash", "label": "qwen3.7-flash（通用，快）"},
                 {"value": "qwen3.7-plus", "label": "qwen3.7-plus（推理型，质量高但慢）"},
             ],
             "placeholder": "留空 = qwen-mt-flash；也可手写网关模型名"},
            # 图片翻译模型：qwen-mt-image-2.0（0.004 元/张，RPM 60 / 并发 2）；失败自动降级到备用模型
            {"name": "image_model", "label": "图片翻译模型", "type": "combo", "default": "qwen-mt-image-2.0",
             "when_flow": ["flow.translate.image", "flow.translate.pdf.image"],
             "options": [
                 {"value": "qwen-mt-image-2.0", "label": "qwen-mt-image-2.0（0.004 元/张，RPM 60）"},
                 {"value": "qwen-mt-image", "label": "qwen-mt-image（备用）"},
             ],
             "placeholder": "留空 = qwen-mt-image-2.0；失败自动用备用模型"},
            # 业务领域（图片翻译的 domainHint）：模版可声明默认，工作台可手写覆盖
            {"name": "image_domain_hint", "label": "业务领域", "type": "combo",
             "when_flow": ["flow.translate.image", "flow.translate.pdf.image"],
             "options": [
                 {"value": "审计财务", "label": "审计财务"},
                 {"value": "通用", "label": "通用（不限定领域）"},
             ],
             "placeholder": "如 审计财务；留空则用模版的领域声明"},
            {"name": "mode", "label": "输出模式", "type": "select", "default": "overlay",
             "when_flow": ["flow.translate.pdf.layout", "flow.translate.docx"],
             # 同一参数在不同流下默认不同：PDF 版式默认原位覆盖，Word 默认双语对照
             "default_by_flow": {"flow.translate.docx": "bilingual"},
             "options": [
                 {"value": "overlay", "label": "原位覆盖（单语译文）"},
                 {"value": "bilingual", "label": "双语对照"},
             ]},
        ],
        "templatesPath": "/translate/templates",
        "dictPath": "/translate/dict",
        # 批量入口声明（存在才显示「单文件 / 批量」切换）；extensions 须与 routes 的后缀一致
        "batch": {
            "extensions": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".md",
                           ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"],
            "maxFiles": 200,
            "maxTotalMB": 500,
        },
        # 目标/源语言候选（值须为引擎可识别语言名）
        "languages": [
            {"value": "Chinese", "label": "中文"},
            {"value": "English", "label": "英文"},
            {"value": "Japanese", "label": "日文"},
            {"value": "Korean", "label": "韩文"},
        ],
        "description": (
            "Translee 全自动翻译：上传 xlsx 表格 / pdf 文档（含扫描/图片版，自动 OCR 补文字层）/ txt 文本 /"
            " docx 文档（正文与表格，支持段落对照双语或原位覆盖）→ 提取可译单元 → 批量翻译 → 保真质检 → 回填；"
            "pdf 可选版式翻译（原位覆盖单语 / 左右分栏双语对照 PDF）或双语 docx；"
            "支持整目录 / 压缩包批量上传（一文件一任务，各自留记录与产物）与翻译模版（语言对/术语表/模型）、已译字典浏览。"
        ),
        "empty_hint": "暂无翻译流——先运行 scripts/register_translee_flows.py 注册翻译流。",
    },
}
