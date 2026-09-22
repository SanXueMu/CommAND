-- 注册表迁移留档（蓝图「飞升」§快速启动）：每次 apply 落一行审计，
-- payload 为受限 registration migration JSON（纯数据声明，非 SQL）。

CREATE TABLE IF NOT EXISTS registration_migration (
    id         BIGSERIAL PRIMARY KEY,
    source     TEXT NOT NULL DEFAULT 'upload',
    payload    JSONB NOT NULL,
    checksum   TEXT NOT NULL,
    applied    BOOLEAN NOT NULL DEFAULT TRUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
