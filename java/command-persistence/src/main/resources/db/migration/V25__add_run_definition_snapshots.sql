CREATE TABLE run_definition_snapshots (
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    definition_kind     TEXT NOT NULL CHECK (definition_kind IN (
        'tool', 'capability_pipeline', 'workflow', 'workbench_view'
    )),
    definition_id       TEXT NOT NULL,
    definition_version  INT NOT NULL CHECK (definition_version > 0),
    schema_version      INT NOT NULL CHECK (schema_version > 0),
    checksum            TEXT NOT NULL,
    document            JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, definition_kind, definition_id, definition_version),
    CHECK (length(checksum) = 64)
);

CREATE INDEX run_definition_snapshots_lookup_idx
    ON run_definition_snapshots (definition_kind, definition_id, definition_version);
