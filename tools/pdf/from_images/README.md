# pdf.from.images — 图片合成 PDF

图片翻译链**第 3 步**：译文页图按页序合成单 PDF。

- 每页按图片像素尺寸建页（保持原页比例，不裁切不变形）
- 命名：`<源文件名>_图片译文.pdf`（未给源文件时回落 `<首图>_图片译文.pdf`）
- **合成成功后清理中间产物**（`cleanup_dirs`：页图目录 + 译文图目录），实现「只留 PDF」
  - 只删 `COMMAND_DATA_DIR` 内的路径，其余记入 `cleanup.skipped`（防误删）
- 回报 `cleanup.removed / files_removed / bytes_freed`

## 注意

输出为**图片版 PDF（无文字层）**：不可选中/搜索/复制。若需要可搜索文字版，请走 `ocrmypdf` 链路（`pdf.extract.pages` 的文字版流）。
