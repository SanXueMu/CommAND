# 修线上 docx 渲染崩溃（S 批次）：提取入口统一清洗 XML 不兼容控制字符

线上现象：识别/翻译 `Material Specfications (2023).pdf` 报
`ValueError: All strings must be XML compatible: Unicode or ASCII, no NULL bytes or control characters`

根因：该 PDF 的文字层含控制字符（C0/C1，来自损坏的字体映射或 OCR 输出），
而提取链路（pdf.extract.pages / pdf.extract.blocks / docx.extract.units / img.vl.extract）
对文本**零清洗**原样透传，最终写入 docx（python-docx 底层 lxml）即抛该错。

修复（S1–S3）：
- S1 新增 `command_shared/text_clean.py::xml_safe_text()`：去除 C0/C1 控制字符、NULL、
  孤立代理对（保留 \t \n \r），最小干预不改内容语义
- S2 提取入口统一应用（一处修、全链受益）+ docx 渲染侧兜底：
  - tools/pdf/extract_pages/main.py（整行级）
  - command_shared/pdf_blocks.py（版式流块文本）
  - command_shared/docx_units.py（Word 段落/表格文本）
  - tools/img/vl_extract/main.py（视觉识别文本落库前）
  - command_shared/docx_render.py（双语/原位渲染兜底，防任何未来路径）
- S3 新增 tests/test_text_clean.py：
  - 单元：控制字符被去除、\t\n\r 与中文保留
  - 集成：pymupdf 构造含 \x00\x01\x0c 文字层的 PDF → extract_pages 输出干净
  - 兜底：脏 segments 直接进 docx 渲染不再抛 ValueError

验证：CommAND 全量 pytest 通过。
