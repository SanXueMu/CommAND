-- 009: 管线删除语义——留档 run 脱钩（方案：C4 重跑留档的延伸）
-- 删除管线定义时，留档 run 的 pipeline_id 置 NULL（保留 run 审计与 steps 数据，
-- 解除 pipeline_runs_pipeline_id_fkey 依赖），删除不再被历史 run 阻断。
ALTER TABLE pipeline_runs ALTER COLUMN pipeline_id DROP NOT NULL;
