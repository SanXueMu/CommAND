CREATE TABLE ocr_templates (
    id TEXT PRIMARY KEY,
    version INT NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
    name TEXT NOT NULL,
    document JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, version)
);

CREATE TABLE ocr_result_sets (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_hash CHAR(64),
    template_id TEXT,
    template_version INT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ocr_records (
    id TEXT PRIMARY KEY,
    result_set_id TEXT NOT NULL REFERENCES ocr_result_sets(id) ON DELETE CASCADE,
    page_no INT,
    record_index INT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ocr_records_result_lookup_idx ON ocr_records(result_set_id, page_no, record_index);

CREATE TABLE ocr_views (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    spec JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
