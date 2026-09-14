# pdf.pages.to_images — PDF 逐页转图片

图片翻译链**第 1 步**（也适用于任何「页图导出」需求）：PDF → 每页图片。

- 命名 `page_0001.jpg`（页序即数组序），页序与裁剪框（`CropBox`）对齐，与全文链一致
- 长边超过 `max_side`（默认 2200px）自动降采样，避免大幅面图纸造成超大图
- `pages` 留空转全部；支持 `format`（jpeg/png）与 `scale`（默认 2.0 ≈ 144dpi）
- **回报 `has_text_layer`**（复用 `is_text_pdf`）：工作台据此判断是文字版还是扫描件
  - 工作台探测走 `GET /api/files/probe`（同判据）；本工具在上传前拦截非 PDF 文件

## 输出

`{file, page_count, rendered, has_text_layer, format, scale, effective_scale, dir, paths[], images[{page,path,width,height}]}`
页面图片为中间产物（写入 `outputs/<handle>/tmp_pages/`），由链末步清理。
