CREATE TABLE llm_settings (
    id TEXT PRIMARY KEY CHECK (id = 'default'),
    base_url TEXT NOT NULL,
    api_key_ciphertext TEXT NOT NULL,
    model TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
