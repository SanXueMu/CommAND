ALTER TABLE llm_settings
    ADD COLUMN models JSONB NOT NULL DEFAULT '[]'::jsonb;
