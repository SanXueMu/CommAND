UPDATE llm_api_keys
SET api_key_suffix = '未知'
WHERE api_key_suffix IS NULL OR api_key_suffix = '';
