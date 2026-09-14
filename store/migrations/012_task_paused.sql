-- 012 任务级暂停：工具抛 ToolPauseError（或子进程退出码 4）时任务落 paused，
-- run 停在该步等人工介入（旧版 .doc 需另存、扫描件需先补文字层等），不消耗重试次数。
-- tasks.status 的 CHECK 需放行 'paused'（原约束名由 PG 自动生成 tasks_status_check）。
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('queued','running','succeeded','failed','failed_review',
                      'cancelled','interrupted','paused'));
