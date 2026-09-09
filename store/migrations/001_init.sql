-- 001_init.sql — CommAND v1 初始结构（依据《CommAND架构蓝图》4.1）

CREATE TABLE tools (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    manifest      JSONB NOT NULL,
    input_types   TEXT[] NOT NULL DEFAULT '{}',
    output_types  TEXT[] NOT NULL DEFAULT '{}',
    runtime_kind  TEXT NOT NULL CHECK (runtime_kind IN ('inproc','subprocess','http')),
    status        TEXT NOT NULL DEFAULT 'active',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    handle        TEXT PRIMARY KEY,
    tool_id       TEXT NOT NULL REFERENCES tools(id),
    input         JSONB NOT NULL,
    output        JSONB,
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','running','succeeded','failed',
                                    'failed_review','cancelled','interrupted')),
    error         JSONB,
    pipeline_run  TEXT,
    step_index    INT NOT NULL DEFAULT 0,
    attempt       INT NOT NULL DEFAULT 1,
    max_attempts  INT NOT NULL DEFAULT 1,
    claimed_by    TEXT,
    heartbeat_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);
CREATE INDEX idx_tasks_queue ON tasks (created_at) WHERE status = 'queued';
CREATE INDEX idx_tasks_pipeline ON tasks (pipeline_run, step_index);

CREATE TABLE task_events (
    id          BIGSERIAL PRIMARY KEY,
    handle      TEXT NOT NULL REFERENCES tasks(handle) ON DELETE CASCADE,
    type        TEXT NOT NULL CHECK (type IN ('log','progress','artifact','status')),
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_handle ON task_events (handle, id);

CREATE TABLE pipelines (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    steps       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tool_relations (
    kind        TEXT NOT NULL CHECK (kind IN ('produces','consumes','composes')),
    from_tool   TEXT NOT NULL REFERENCES tools(id),
    to_tool     TEXT NOT NULL REFERENCES tools(id),
    detail      JSONB,
    PRIMARY KEY (kind, from_tool, to_tool)
);
