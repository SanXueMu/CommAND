package com.zthcpa.command.contract;

import java.util.Objects;

public record DefinitionKey(DefinitionKind kind, String id, int version) {
    public DefinitionKey {
        Objects.requireNonNull(kind, "kind");
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Definition id must not be blank");
        }
        if (version < 1) {
            throw new IllegalArgumentException("Definition version must be positive");
        }
    }
}
