package com.zthcpa.command.persistence.config;

import com.zthcpa.command.contract.LlmConfigurationPort;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class HibernateLlmConfigurationService implements LlmConfigurationPort {
    private static final String DEFAULT_MODEL = "deepseek-v3.2";
    private final EntityManager entityManager;
    private final byte[] masterKey;
    private final SecureRandom random = new SecureRandom();

    public HibernateLlmConfigurationService(EntityManager entityManager) {
        this.entityManager = entityManager;
        String value = System.getenv("COMMAND_LLM_MASTER_KEY");
        this.masterKey = value == null || value.isBlank() ? null : sha256(value);
    }

    @Override
    @Transactional
    public Optional<LlmConfiguration> get() {
        List<LlmApiKeyEntity> keys = activeDefaults();
        if (keys.isEmpty()) return Optional.empty();
        LlmApiKeyEntity key = keys.get(0);
        key.markUsed(Instant.now());
        return Optional.of(new LlmConfiguration(key.getBaseUrl(), decrypt(key.getApiKeyCiphertext()),
                key.getDefaultModel(), normalizeModels(key.getDefaultModel(), key.getModels())));
    }

    @Override
    @Transactional
    public List<LlmApiKey> listKeys() {
        return entityManager.createQuery("select k from LlmApiKeyEntity k order by k.defaultKey desc, k.updatedAt desc", LlmApiKeyEntity.class)
                .getResultList().stream().map(this::toContract).toList();
    }

    @Override
    @Transactional
    public LlmApiKey addKey(String remark, String providerName, String baseUrl, String apiKey,
                            String defaultModel, List<String> models, boolean makeDefault) {
        requireText(apiKey, "apiKey");
        List<String> normalized = normalizeModels(defaultModel, models);
        String resolvedDefault = resolveDefault(defaultModel, normalized);
        boolean first = listKeys().isEmpty();
        LlmApiKeyEntity entity = new LlmApiKeyEntity(UUID.randomUUID(), required(remark, "API Key"),
                defaultText(providerName, "OpenAI 兼容服务"), required(baseUrl, "baseUrl"), encrypt(apiKey), suffix(apiKey),
                normalized, resolvedDefault, true, first || makeDefault, Instant.now(), Instant.now());
        if (entity.isDefaultKey()) unsetDefaults();
        entityManager.persist(entity);
        return toContract(entity);
    }

    @Override
    @Transactional
    public LlmApiKey updateKey(UUID id, String remark, String providerName, String baseUrl,
                               String apiKey, String defaultModel, List<String> models, boolean enabled) {
        LlmApiKeyEntity entity = find(id);
        List<String> normalized = normalizeModels(defaultModel, models);
        String ciphertext = apiKey == null || apiKey.isBlank() ? entity.getApiKeyCiphertext() : encrypt(apiKey);
        entity.update(required(remark, "remark"), defaultText(providerName, "OpenAI 兼容服务"), required(baseUrl, "baseUrl"),
                ciphertext, apiKey == null || apiKey.isBlank() ? entity.getApiKeySuffix() : suffix(apiKey), normalized,
                resolveDefault(defaultModel, normalized), enabled, Instant.now());
        if (!enabled && entity.isDefaultKey()) throw new IllegalArgumentException("请先切换默认 API Key，再停用当前默认 Key");
        return toContract(entity);
    }

    @Override
    @Transactional
    public void setDefault(UUID id) {
        LlmApiKeyEntity entity = find(id);
        if (!entity.isEnabled()) throw new IllegalArgumentException("不能将已停用的 API Key 设为默认");
        unsetDefaults();
        entity.markDefault(true);
    }

    @Override
    @Transactional
    public void deleteKey(UUID id) {
        LlmApiKeyEntity entity = find(id);
        if (entity.isDefaultKey()) throw new IllegalArgumentException("请先切换默认 API Key，再删除当前默认 Key");
        entityManager.remove(entity);
    }

    @Override
    @Transactional
    public void clear() {
        entityManager.createQuery("delete from LlmApiKeyEntity").executeUpdate();
    }

    private List<LlmApiKeyEntity> activeDefaults() {
        return entityManager.createQuery("select k from LlmApiKeyEntity k where k.defaultKey = true and k.enabled = true", LlmApiKeyEntity.class).getResultList();
    }

    private LlmApiKeyEntity find(UUID id) {
        LlmApiKeyEntity entity = entityManager.find(LlmApiKeyEntity.class, id);
        if (entity == null) throw new IllegalArgumentException("API Key 不存在: " + id);
        return entity;
    }

    private void unsetDefaults() {
        entityManager.createQuery("update LlmApiKeyEntity k set k.defaultKey = false where k.defaultKey = true").executeUpdate();
    }

    private LlmApiKey toContract(LlmApiKeyEntity entity) {
        return new LlmApiKey(entity.getId(), entity.getRemark(), entity.getProviderName(), entity.getBaseUrl(), entity.getApiKeySuffix(),
                normalizeModels(entity.getDefaultModel(), entity.getModels()), entity.getDefaultModel(), entity.isEnabled(), entity.isDefaultKey(),
                entity.getCreatedAt(), entity.getUpdatedAt(), entity.getLastUsedAt());
    }

    private static List<String> normalizeModels(String defaultModel, List<String> models) {
        LinkedHashSet<String> result = new LinkedHashSet<>();
        if (defaultModel != null && !defaultModel.isBlank()) result.add(defaultModel.trim());
        if (models != null) for (String model : models) if (model != null && !model.isBlank()) result.add(model.trim());
        if (result.isEmpty()) result.add(DEFAULT_MODEL);
        return new ArrayList<>(result);
    }

    private static String resolveDefault(String defaultModel, List<String> models) {
        return defaultModel != null && models.contains(defaultModel.trim()) ? defaultModel.trim() : models.get(0);
    }
    private static String required(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " must not be blank"); return value.trim(); }
    private static String requireText(String value, String field) { return required(value, field); }
    private static String defaultText(String value, String fallback) { return value == null || value.isBlank() ? fallback : value.trim(); }
    private static String suffix(String value) { return value.length() <= 4 ? value : value.substring(value.length() - 4); }

    private String encrypt(String value) {
        try { byte[] nonce = new byte[12]; random.nextBytes(nonce); Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(requireMasterKey(), "AES"), new GCMParameterSpec(128, nonce)); byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)); return Base64.getEncoder().encodeToString(ByteBuffer.allocate(nonce.length + encrypted.length).put(nonce).put(encrypted).array()); }
        catch (Exception exception) { throw new IllegalStateException("Unable to encrypt LLM API key", exception); }
    }
    private String decrypt(String value) {
        try { byte[] packed = Base64.getDecoder().decode(value); byte[] nonce = java.util.Arrays.copyOfRange(packed, 0, 12); byte[] data = java.util.Arrays.copyOfRange(packed, 12, packed.length); Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(requireMasterKey(), "AES"), new GCMParameterSpec(128, nonce)); return new String(cipher.doFinal(data), StandardCharsets.UTF_8); }
        catch (Exception exception) { throw new IllegalStateException("Unable to decrypt LLM API key", exception); }
    }
    private byte[] requireMasterKey() { if (masterKey == null) throw new IllegalStateException("COMMAND_LLM_MASTER_KEY must be set to manage stored LLM configuration"); return masterKey; }
    private static byte[] sha256(String value) { try { return MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)); } catch (Exception exception) { throw new IllegalStateException(exception); } }
}
