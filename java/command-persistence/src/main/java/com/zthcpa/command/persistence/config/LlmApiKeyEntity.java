package com.zthcpa.command.persistence.config;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "llm_api_keys", schema = "command_runtime")
public class LlmApiKeyEntity {
    @Id
    private UUID id;
    @Column(nullable = false)
    private String remark;
    @Column(name = "provider_name", nullable = false)
    private String providerName;
    @Column(name = "base_url", nullable = false)
    private String baseUrl;
    @Column(name = "api_key_ciphertext", nullable = false)
    private String apiKeyCiphertext;
    @Column(name = "api_key_suffix", nullable = false)
    private String apiKeySuffix;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private List<String> models = new ArrayList<>();
    @Column(name = "default_model", nullable = false)
    private String defaultModel;
    @Column(nullable = false)
    private boolean enabled;
    @Column(name = "is_default", nullable = false)
    private boolean defaultKey;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
    @Column(name = "last_used_at")
    private Instant lastUsedAt;

    protected LlmApiKeyEntity() {}

    public LlmApiKeyEntity(UUID id, String remark, String providerName, String baseUrl,
                           String apiKeyCiphertext, String apiKeySuffix, List<String> models,
                           String defaultModel, boolean enabled, boolean defaultKey,
                           Instant createdAt, Instant updatedAt) {
        this.id = id;
        this.remark = remark;
        this.providerName = providerName;
        this.baseUrl = baseUrl;
        this.apiKeyCiphertext = apiKeyCiphertext;
        this.apiKeySuffix = apiKeySuffix;
        this.models = models;
        this.defaultModel = defaultModel;
        this.enabled = enabled;
        this.defaultKey = defaultKey;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public UUID getId() { return id; }
    public String getRemark() { return remark; }
    public String getProviderName() { return providerName; }
    public String getBaseUrl() { return baseUrl; }
    public String getApiKeyCiphertext() { return apiKeyCiphertext; }
    public String getApiKeySuffix() { return apiKeySuffix; }
    public List<String> getModels() { return models; }
    public String getDefaultModel() { return defaultModel; }
    public boolean isEnabled() { return enabled; }
    public boolean isDefaultKey() { return defaultKey; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getLastUsedAt() { return lastUsedAt; }

    public void update(String remark, String providerName, String baseUrl, String ciphertext,
                       String suffix, List<String> models, String defaultModel,
                       boolean enabled, Instant updatedAt) {
        this.remark = remark;
        this.providerName = providerName;
        this.baseUrl = baseUrl;
        this.apiKeyCiphertext = ciphertext;
        this.apiKeySuffix = suffix;
        this.models = models;
        this.defaultModel = defaultModel;
        this.enabled = enabled;
        this.updatedAt = updatedAt;
    }

    public void markDefault(boolean value) { this.defaultKey = value; }
    public void markUsed(Instant value) { this.lastUsedAt = value; }
}
