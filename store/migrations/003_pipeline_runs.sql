-- 003: 管线运行实体化——原始 input 跨步引用的存放处（蓝图最小必要补全）
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL REFERENCES pipelines(id),
    input       JSONB NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','succeeded','failed','failed_review','cancelled','interrupted')),
    error       JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
