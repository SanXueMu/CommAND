package com.zthcpa.command.contract;

import java.util.Map;
import java.util.Objects;

public record RunDefinitionSnapshot(
        String runId,
        DefinitionKey key,
        int schemaVersion,
        String checksum,
        Map<String, Object> document
) {
    public RunDefinitionSnapshot {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        Objects.requireNonNull(key, "key");
        if (schemaVersion < 1) {
            throw new IllegalArgumentException("Schema version must be positive");
        }
        if (checksum == null || !checksum.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Snapshot checksum must be a lowercase SHA-256 hex value");
        }
        document = Map.copyOf(Objects.requireNonNull(document, "document"));
    }
}
