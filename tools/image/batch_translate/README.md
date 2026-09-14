# image.batch.translate — 图片翻译（批量）

图片翻译链**第 2 步**：图片序列 → 译文图片序列（保留排版，原位替换文字）。

- 逐张复用单图流程：`getPolicy` 取临时上传凭证 → OSS 直传 → 异步 `image2image/image-synthesis` → 轮询 → 下载译文图
- **并发 2**（平台限制）+ **全局 RPM 限速**（`qwen-mt-image-2.0` 为 60，即约 1 秒/张）；429 指数退避
- **逐页回报**：单页失败不中断整批（`images[].ok/error`）；全部失败才抛错并附原因摘要
- **页数上限 500**（平台异步队列上限）：超出直接拒绝并提示拆分
- 主模型不可用/失败 → 自动降级 `fallback_model`（默认 `qwen-mt-image`）
- 术语干预：`terms` 直通 `ext.terminologies`；`domain_hint` 传业务域（如「审计财务」）
- 约束：源或目标语言至少一方为中文/英文；译文图写入 `outputs/<handle>/tmp_mt_images/`（中间产物，末步清理）

## 计费

按成功张数计费：`usage.image_count × 0.004 元`（129 页 ≈ 0.52 元）。
