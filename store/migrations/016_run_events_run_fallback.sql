-- 016：审计事件词表扩容 —— run 级失败降级 run_fallback（H7）
-- 背景：图片翻译流遇「模型不可用」（ToolUnavailableError）时，按管线 on_failure.fallback_flow
--       自动新起一条降级 run（如图片版 PDF → 版式翻译）。原 run 与新 run 各留一条 run_fallback。
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
    'run_fallback'));
