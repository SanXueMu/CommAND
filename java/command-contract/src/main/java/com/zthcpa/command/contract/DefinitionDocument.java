package com.zthcpa.command.contract;

import java.util.Map;
import java.util.Objects;

public record DefinitionDocument(
        DefinitionKey key,
        int schemaVersion,
        DefinitionStatus status,
        Map<String, Object> content,
        String checksum,
        String source
) {
    public DefinitionDocument {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(status, "status");
        if (schemaVersion < 1) {
            throw new IllegalArgumentException("Schema version must be positive");
        }
        content = Map.copyOf(Objects.requireNonNull(content, "content"));
        if (checksum == null || !checksum.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Definition checksum must be a lowercase SHA-256 hex value");
        }
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Definition source must not be blank");
        }
    }
}
