package com.zthcpa.command.contract;

import java.util.List;
import java.util.Optional;
import java.time.Instant;
import java.util.UUID;

public interface LlmConfigurationPort {
    Optional<LlmConfiguration> get();
    List<LlmApiKey> listKeys();
    LlmApiKey addKey(String remark, String providerName, String baseUrl, String apiKey,
                     String defaultModel, List<String> models, boolean makeDefault);
    LlmApiKey updateKey(UUID id, String remark, String providerName, String baseUrl,
                        String apiKey, String defaultModel, List<String> models, boolean enabled);
    void setDefault(UUID id);
    void deleteKey(UUID id);
    void clear();

    record LlmConfiguration(String baseUrl, String apiKey, String model, List<String> models) {
        public LlmConfiguration {
            models = models == null ? List.of() : List.copyOf(models);
        }
    }

    record LlmApiKey(
            UUID id,
            String remark,
            String providerName,
            String baseUrl,
            String apiKeySuffix,
            List<String> models,
            String defaultModel,
            boolean enabled,
            boolean isDefault,
            Instant createdAt,
            Instant updatedAt,
            Instant lastUsedAt
    ) {
        public LlmApiKey {
            models = models == null ? List.of() : List.copyOf(models);
        }
    }
}
