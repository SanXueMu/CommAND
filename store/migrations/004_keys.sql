-- 004: keys 服务——LLM 密钥命名管理（CommAND 级，工具运行时经 ctx 注入）
CREATE TABLE IF NOT EXISTS keys (
    name        TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    api_key     TEXT NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
