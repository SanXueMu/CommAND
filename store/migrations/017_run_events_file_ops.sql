-- 017：审计事件词表扩容 —— 任务级文件/参数修正（N3）
-- file_replaced：替换任务原件（如旧版 .doc 另存为 .docx 后上传替换）
-- input_updated：就地修正任务参数（密钥名、模型、术语等）后继续/重跑
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
    'file_replaced', 'input_updated'));
