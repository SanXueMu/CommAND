-- 011: run_events 级联删除——删除任务不再被审计事件外键阻断（500 修复）
-- 根因：006 建表时 run_id REFERENCES pipeline_runs(id) 未声明 ON DELETE（默认为 NO ACTION），
--       而 delete_run 只解绑 tasks 再删 run/pipeline_runs，从不删 run_events
--       → 有审计事件的 run 删除必然 ForeignKeyViolation → API 500 Internal Server Error。
-- 影响：翻译工作台「删除任务」报 500（示例 run p_3dde225645787656 有 4 条事件）。
ALTER TABLE run_events DROP CONSTRAINT IF EXISTS run_events_run_id_fkey;
ALTER TABLE run_events ADD CONSTRAINT run_events_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE;
