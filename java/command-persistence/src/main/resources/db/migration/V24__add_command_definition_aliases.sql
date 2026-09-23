CREATE TABLE command_definition_aliases (
    alias_id            TEXT NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN (
        'capability_pipeline', 'workflow', 'workbench_view'
    )),
    target_id           TEXT NOT NULL,
    target_version      INT NOT NULL CHECK (target_version > 0),
    status              TEXT NOT NULL CHECK (status IN (
        'active', 'deprecated', 'retired'
    )),
    reason              TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at          TIMESTAMPTZ,
    PRIMARY KEY (kind, alias_id),
    CHECK (alias_id <> target_id)
);

CREATE INDEX command_definition_alias_target_idx
    ON command_definition_aliases (kind, target_id, target_version);
