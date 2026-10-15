CREATE TABLE llm_api_keys (
    id UUID PRIMARY KEY,
    remark TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key_ciphertext TEXT NOT NULL,
    api_key_suffix TEXT NOT NULL,
    models JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_model TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_llm_api_keys_single_default
    ON llm_api_keys (is_default)
    WHERE is_default = TRUE;

INSERT INTO llm_api_keys (
    id, remark, provider_name, base_url, api_key_ciphertext, api_key_suffix,
    models, default_model, enabled, is_default, created_at, updated_at
)
SELECT
    '00000000-0000-0000-0000-000000000001'::uuid,
    '旧版默认 LLM 配置',
    CASE
        WHEN base_url ILIKE '%dashscope.aliyuncs.com%' THEN '阿里云百炼'
        ELSE 'OpenAI 兼容服务'
    END,
    base_url,
    api_key_ciphertext,
    '未知',
    CASE
        WHEN jsonb_array_length(models) > 0 THEN models
        ELSE jsonb_build_array(model)
    END,
    model,
    TRUE,
    TRUE,
    now(),
    now()
FROM llm_settings
WHERE id = 'default'
  AND NOT EXISTS (SELECT 1 FROM llm_api_keys);
