-- 008: 调整流——三级概念 + 嵌套 run 树 + 工具启停显隐 + 流输入 schema（方案：06架构升级-调整流.md §四/§五 + 07嵌套执行详细设计.md §二）

-- 1) 三级概念：pipelines.type（flow=普通流 steps 全引工具；workflow=工作流 steps 可引普通流；两层限深）
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'flow';
ALTER TABLE pipelines DROP CONSTRAINT IF EXISTS pipelines_type_check;
ALTER TABLE pipelines ADD CONSTRAINT pipelines_type_check CHECK (type IN ('flow','workflow'));

-- 2) 流级输入 schema（声明式表单，CommWEB FlowRunner 从猜键变声明驱动；06 P2）
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS input_schema JSONB;

-- 3) 嵌套 run 树（07 §二）：parent_step_index 反查免扫描
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS parent_run_id TEXT REFERENCES pipeline_runs(id);
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS parent_step_index INT;
CREATE INDEX IF NOT EXISTS idx_runs_parent ON pipeline_runs(parent_run_id, parent_step_index);

-- 4) 工具显隐（06 D1：enabled 复用 tools.status active/disabled；hidden 独立显隐属性）
ALTER TABLE tools ADD COLUMN IF NOT EXISTS hidden BOOLEAN NOT NULL DEFAULT false;

-- 审计事件词表扩容：subrun_created / subrun_finished / step_skipped / flow_rerun（07 §六 + 06 D2/C4）
ALTER TABLE run_events DROP CONSTRAINT IF EXISTS run_events_kind_check;
ALTER TABLE run_events ADD CONSTRAINT run_events_kind_check CHECK (kind IN (
    'created', 'step_queued', 'step_started',
    'step_completed', 'step_failed', 'step_cancelled', 'step_skipped',
    'pause_requested', 'paused_at_boundary',
    'resume_requested', 'resumed',
    'abort_requested', 'run_aborted', 'step_abort',
    'rerun_requested', 'step_rerun', 'flow_rerun',
    'override_applied',
    'subrun_created', 'subrun_finished'));
