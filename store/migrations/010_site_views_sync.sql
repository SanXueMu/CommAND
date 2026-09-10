-- 010: site_views 内置标记 + seed 同步化——OCR 四视图残留根因修复。
-- 旧 seed 只 upsert 不删：代码删掉 OCR 识别/结果/导出/模版生成四视图后，
-- 已部署库（41）的旧行永不清除，/meta/site 继续下发 → 顶部 Tab 残留。
-- is_builtin 标记内置声明来源；seed 同步化时删除「内置但不在当前清单」的行。
ALTER TABLE site_views ADD COLUMN IF NOT EXISTS is_builtin BOOLEAN NOT NULL DEFAULT FALSE;
