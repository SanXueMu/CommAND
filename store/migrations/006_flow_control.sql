-- 006: 流的全控制——paused 状态 + progress 指针 + run 级审计事件表（方案：架构升级-流的全控制.md §6）

-- 1) run 状态机扩容：paused（非终态、可恢复）
ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_status_check;
ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_status_check
    CHECK (status IN ('running','paused','succeeded','failed','failed_review',
                      'cancelled','interrupted'));
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS progress INT;
CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status, created_at DESC);

-- 2) run 级操作审计（append-only，工单的「审批记录」）
CREATE TABLE IF NOT EXISTS run_events (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES pipeline_runs(id),
    task_handle  TEXT,
    kind         TEXT NOT NULL CHECK (kind IN (
        'created', 'step_queued', 'step_started',
        'step_completed', 'step_failed', 'step_cancelled',
        'pause_requested', 'paused_at_boundary',
        'resume_requested', 'resumed',
        'abort_requested', 'run_aborted', 'step_abort',
        'rerun_requested', 'step_rerun',
        'override_applied')),
    actor        TEXT NOT NULL DEFAULT 'console',
    detail       JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, id);
