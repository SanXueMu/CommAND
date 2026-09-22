package com.zthcpa.command.contract;

import java.util.Map;
import java.util.Objects;

public record ToolDescriptor(
        ToolKey key,
        RuntimeKind runtimeKind,
        String status,
        Map<String, Object> manifest
) {
    public ToolDescriptor {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(runtimeKind, "runtimeKind");
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Tool status must not be blank");
        }
        manifest = Map.copyOf(Objects.requireNonNull(manifest, "manifest"));
    }
}
