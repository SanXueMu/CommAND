-- 005: 管线文档——专业化介绍的 md 全文（工具侧 doc_md 住 manifest JSONB，无需建列）
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS doc_md TEXT;
