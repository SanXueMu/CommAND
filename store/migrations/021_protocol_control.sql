-- 协议控制面（蓝图「飞升」§会员映像与同步状态机）：四表分层。
-- 协议发布注册 / 会员原始映像（不可变）/ 投影映像（可再生成）/ 同步运行记录。

-- 协议发布：一次协议演进 = 一行（Core / Extension / Snapshot 三层口径）。
CREATE TABLE IF NOT EXISTS protocol_release (
    id              INT PRIMARY KEY,
    core            INT NOT NULL,
    extensions      JSONB NOT NULL DEFAULT '{}',
    snapshot_schema INT NOT NULL DEFAULT 1,
    notes           TEXT,
    released_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 会员原始映像：采集即固化（无 UPDATE 路径）；同步只读它、永不改写。
CREATE TABLE IF NOT EXISTS provider_snapshot (
    id             BIGSERIAL PRIMARY KEY,
    provider_id    TEXT NOT NULL,
    release_id     INT NOT NULL REFERENCES protocol_release(id),
    schema_version INT NOT NULL,
    payload        JSONB NOT NULL,
    checksum       TEXT NOT NULL,
    captured_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_provider_snapshot_latest
    ON provider_snapshot (provider_id, id DESC);

-- 投影映像：按目标 release 从原始映像生成；is_current 行即对外生效的那份。
-- 失败/不兼容不触碰旧行（保留上一次成功投影），升级 = 原子翻转 is_current。
CREATE TABLE IF NOT EXISTS provider_projection (
    id           BIGSERIAL PRIMARY KEY,
    provider_id  TEXT NOT NULL,
    snapshot_id  BIGINT NOT NULL REFERENCES provider_snapshot(id),
    release_id   INT NOT NULL REFERENCES protocol_release(id),
    payload      JSONB NOT NULL,
    checksum     TEXT NOT NULL,
    is_current   BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_projection_current
    ON provider_projection (provider_id) WHERE is_current;

-- 同步运行：状态机 PENDING→VALIDATING→MIGRATING→SUCCEEDED/FAILED/INCOMPATIBLE。
-- 幂等凭据 = (provider_id, snapshot_id, to_release_id) 已 SUCCEEDED 的 run 重放直接命中。
CREATE TABLE IF NOT EXISTS provider_sync_run (
    id              BIGSERIAL PRIMARY KEY,
    provider_id     TEXT NOT NULL,
    snapshot_id     BIGINT NOT NULL REFERENCES provider_snapshot(id),
    from_release_id INT,
    to_release_id   INT NOT NULL REFERENCES protocol_release(id),
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING','VALIDATING','MIGRATING','SUCCEEDED','FAILED','INCOMPATIBLE')),
    error           TEXT,
    checksum        TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_provider_sync_run_latest
    ON provider_sync_run (provider_id, id DESC);
