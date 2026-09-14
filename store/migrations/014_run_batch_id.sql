-- 014 批次概念：一次目录/压缩包上传 = 一个批次（batch_id），run 记录自己属于哪个批次。
-- 导出时按 data/batches/<batch_id>.json 清单还原原目录结构（清单由上传端点写，见 files_router）。
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS batch_id TEXT;

CREATE INDEX IF NOT EXISTS pipeline_runs_batch_idx ON pipeline_runs (batch_id);
