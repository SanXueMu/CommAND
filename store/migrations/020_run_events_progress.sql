-- AI1：工具进度消息 progress 进审计总线（run_events）
-- 此前只写 task_events（工具流），run_events 侧 latest_progress_bulk 查 kind='progress' 恒空
ALTER TABLE run_events DROP CONSTRAINT IF EXISTS run_events_kind_check;
ALTER TABLE run_events ADD CONSTRAINT run_events_kind_check CHECK (kind IN (
    'created', 'step_queued', 'step_started',
    'step_completed', 'step_failed', 'step_cancelled', 'step_skipped', 'step_paused',
    'pause_requested', 'paused_at_boundary',
    'resume_requested', 'resumed',
    'abort_requested', 'run_aborted', 'step_abort',
    'rerun_requested', 'step_rerun', 'flow_rerun',
    'override_applied',
    'subrun_created', 'subrun_finished',
    'run_fallback',
    'file_replaced', 'input_updated',
    'run_recovered', 'artifacts_purged', 'progress'
));
