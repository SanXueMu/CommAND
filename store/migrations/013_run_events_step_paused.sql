-- 013：审计事件词表扩容 —— 任务级暂停 step_paused（E2）
-- 背景：工具抛 ToolPauseError（旧版 .doc 需另存、扫描件需先补文字层等）时任务落 paused，
--       该步在 run_events 留一条 step_paused（区别于 step_failed：不级联收口，resume 可续跑）。
-- 注：012 已扩 tasks.status 的 CHECK；事件词表在 008 定义，此处追加扩容。
ALTER TABLE run_events DROP CONSTRAINT IF EXISTS run_events_kind_check;
ALTER TABLE run_events ADD CONSTRAINT run_events_kind_check CHECK (kind IN (
    'created', 'step_queued', 'step_started',
    'step_completed', 'step_failed', 'step_cancelled', 'step_skipped', 'step_paused',
    'pause_requested', 'paused_at_boundary',
    'resume_requested', 'resumed',
    'abort_requested', 'run_aborted', 'step_abort',
    'rerun_requested', 'step_rerun', 'flow_rerun',
    'override_applied',
    'subrun_created', 'subrun_finished'));
