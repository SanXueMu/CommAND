CREATE TABLE command_definitions (
    id                  TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN (
        'capability_pipeline', 'workflow', 'workbench_view'
    )),
    definition_version  INT NOT NULL CHECK (definition_version > 0),
    schema_version      INT NOT NULL CHECK (schema_version > 0),
    status              TEXT NOT NULL CHECK (status IN (
        'draft', 'active', 'deprecated', 'retired'
    )),
    document            JSONB NOT NULL,
    checksum            TEXT NOT NULL,
    owner               TEXT NOT NULL DEFAULT 'command',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, id, definition_version),
    CHECK (length(trim(id)) > 0),
    CHECK (length(checksum) = 64)
);

CREATE UNIQUE INDEX command_definitions_active_idx
    ON command_definitions (kind, id)
    WHERE status = 'active';

CREATE INDEX command_definitions_lookup_idx
    ON command_definitions (kind, id, status);
