package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionKey;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public record RunSnapshot(
        String id,
        DefinitionKey workflow,
        RunStatus status,
        Map<String, Object> input,
        Map<String, Object> error,
        Instant createdAt,
        Instant finishedAt
) {
    public RunSnapshot {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        Objects.requireNonNull(workflow, "workflow");
        Objects.requireNonNull(status, "status");
        input = Map.copyOf(Objects.requireNonNull(input, "input"));
        error = error == null ? null : Map.copyOf(error);
        Objects.requireNonNull(createdAt, "createdAt");
    }
}
