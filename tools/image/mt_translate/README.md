# image.mt.translate — 图片翻译

本地图片 → DashScope 临时上传 → **异步图片翻译**（`qwen-mt-image-2.0`）→ 下载译文图。

## 入参

| 参数 | 说明 |
|---|---|
| `file` | 图片路径（png/jpg/jpeg/webp/tif/tiff/bmp） |
| `model` | 默认 `qwen-mt-image-2.0`（**0.004 元/张**，RPM=1） |
| `fallback_model` | 默认 `qwen-mt-image`：主模型不可用/任务失败**自动降级**（同端点，仅模型名不同） |
| `source_lang` / `target_lang` | 留空源语言自动识别；**源或目标至少一方须为中文/英文** |
| `terms` | 术语干预：`[[原文,译文]]` 或每行「原文 => 译文」→ `terminologies[{src,tgt}]` |
| `domain_hint` | 领域提示（如 finance/legal） |
| `sensitives` | 不翻译的敏感词 |
| `image_segment` | 仅翻译主体区域（商品图场景） |
| `key_name` | 密钥名；留空用默认密钥（DashScope） |
| `base_url` | 原生 API 地址；留空由密钥 base_url 自动推导（`/compatible-mode/v1` → 原生根） |

## 出参

`path`（译文图，落 `outputs/<handle>/`）、`name`、`model`（实际使用）、`fallback_used`、
`task_id`、`image_count`（计费张数）、`elapsed_s`、`waited_s`（限速等待）。

## 约束与注意

- 只能**异步**：提交 → 轮询 `/api/v1/tasks/{id}` → 结果 URL **24h 失效**，工具会立即下载落盘
- `qwen-mt-image-2.0` **RPM = 1** → 每张图提交间隔 ≥60s（工具内置跨线程限速 + 429 指数退避）；
  批量/扫描件页级翻译请谨慎评估耗时（每页约 1 分钟）
- 原图只读；失败降级会在事件流里 emit `fallback`（含降级原因）
