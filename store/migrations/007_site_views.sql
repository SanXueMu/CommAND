-- 007: 站点视图声明表——会员业务声明数据化（纯壳准则：CommWEB 代码零业务内容，
-- 声明经 /meta/site 下发；启动 seed 幂等写入，热部署即生效）。
CREATE TABLE IF NOT EXISTS site_views (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    icon TEXT,
    when_capability TEXT,
    props JSONB NOT NULL DEFAULT '{}',
    sort INTEGER NOT NULL DEFAULT 100,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
