package com.zthcpa.command.contract;

import java.util.Objects;

public record ToolKey(String id, int version) {
    public ToolKey {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Tool id must not be blank");
        }
        if (version < 1) {
            throw new IllegalArgumentException("Tool version must be positive");
        }
    }
}
