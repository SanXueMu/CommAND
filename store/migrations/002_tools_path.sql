-- 002: 工具落位路径（注册时写入，目录名与 id 解耦）
ALTER TABLE tools ADD COLUMN IF NOT EXISTS path TEXT;
