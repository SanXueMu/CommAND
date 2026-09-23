CREATE TABLE command_definitions (
    kind                TEXT NOT NULL CHECK (kind IN ('tool', 'capability_pipeline', 'workflow', 'workbench_view')),
    id                  TEXT NOT NULL,
    definition_version  INT NOT NULL CHECK (definition_version > 0),
    schema_version      INT NOT NULL CHECK (schema_version > 0),
    status              TEXT NOT NULL CHECK (status IN ('draft', 'active', 'deprecated', 'retired')),
    document            JSONB NOT NULL,
    checksum            CHAR(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    owner               TEXT NOT NULL DEFAULT 'command',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, id, definition_version),
    CHECK (length(trim(id)) > 0)
);

CREATE UNIQUE INDEX command_definitions_active_idx
    ON command_definitions (kind, id)
    WHERE status = 'active';

CREATE TABLE runs (
    id                  TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL,
    workflow_version    INT NOT NULL CHECK (workflow_version > 0),
    input               JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL CHECK (status IN (
        'running', 'paused', 'succeeded', 'failed', 'failed_review', 'cancelled', 'interrupted'
    )),
    error               JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ
);

CREATE INDEX runs_workflow_lookup_idx
    ON runs (workflow_id, workflow_version, created_at DESC);

CREATE TABLE run_definition_snapshots (
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    definition_kind     TEXT NOT NULL CHECK (definition_kind IN ('tool', 'capability_pipeline', 'workflow', 'workbench_view')),
    definition_id       TEXT NOT NULL,
    definition_version  INT NOT NULL CHECK (definition_version > 0),
    schema_version      INT NOT NULL CHECK (schema_version > 0),
    checksum            CHAR(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    document            JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, definition_kind, definition_id, definition_version)
);

CREATE TABLE run_steps (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_index          INT NOT NULL CHECK (step_index >= 0),
    step_key            TEXT NOT NULL,
    definition_kind     TEXT NOT NULL CHECK (definition_kind IN ('tool', 'capability_pipeline')),
    definition_id       TEXT NOT NULL,
    definition_version  INT NOT NULL CHECK (definition_version > 0),
    input               JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL CHECK (status IN (
        'pending', 'queued', 'running', 'paused', 'succeeded', 'failed', 'cancelled', 'skipped'
    )),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    UNIQUE (run_id, step_index)
);

CREATE TABLE task_executions (
    id                  TEXT PRIMARY KEY,
    step_id             TEXT NOT NULL REFERENCES run_steps(id) ON DELETE CASCADE,
    attempt              INT NOT NULL CHECK (attempt > 0),
    max_attempts        INT NOT NULL CHECK (max_attempts > 0),
    worker_id           TEXT,
    input               JSONB NOT NULL DEFAULT '{}',
    output              JSONB,
    error               JSONB,
    status              TEXT NOT NULL CHECK (status IN (
        'queued', 'running', 'succeeded', 'failed', 'failed_review', 'cancelled', 'interrupted'
    )),
    heartbeat_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    UNIQUE (step_id, attempt)
);

CREATE INDEX task_executions_queue_idx
    ON task_executions (created_at)
    WHERE status = 'queued';

CREATE TABLE run_events (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id             TEXT REFERENCES run_steps(id) ON DELETE SET NULL,
    kind                TEXT NOT NULL,
    actor               TEXT NOT NULL DEFAULT 'system',
    detail              JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX run_events_lookup_idx ON run_events (run_id, id);

CREATE TABLE task_events (
    id                  BIGSERIAL PRIMARY KEY,
    task_id             TEXT NOT NULL REFERENCES task_executions(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL,
    detail              JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX task_events_lookup_idx ON task_events (task_id, id);

CREATE TABLE artifacts (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id             TEXT REFERENCES run_steps(id) ON DELETE SET NULL,
    artifact_kind       TEXT NOT NULL,
    storage_key         TEXT NOT NULL,
    media_type          TEXT,
    size_bytes          BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    checksum            CHAR(64) CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX artifacts_run_lookup_idx ON artifacts (run_id, created_at);
