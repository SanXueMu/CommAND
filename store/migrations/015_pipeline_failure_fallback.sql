-- 015: 流级失败降级（on_failure）+ 降级 run 溯源（fallback_of）
--
-- 场景：图片版 PDF 翻译（flow.translate.pdf.image）依赖 qwen-mt-image 模型；该模型未开通 /
-- 无权限 / 不存在时，重试无意义，应自动改用等价流（版式翻译 flow.translate.pdf.layout，
-- 内部自带 ocrmypdf 补文字层）——即用户口径的「走原方案」。
--
-- on_failure 形态：{"fallback_flow": "<flow id>"}（可扩展其它策略，如 {"notify": true}）
-- fallback_of：降级 run 记录它由哪条 run 降级而来（原 run 保持 failed 留档，便于追溯/导出取用）
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS on_failure JSONB;

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS fallback_of TEXT;
