package com.zthcpa.command.run;

import com.zthcpa.command.contract.ToolKey;

import java.util.Map;
import java.util.Objects;

public record TaskSnapshot(
        String handle,
        ToolKey tool,
        TaskStatus status,
        Map<String, Object> input,
        Map<String, Object> output,
        Map<String, Object> error,
        int attempt,
        int maxAttempts
) {
    public TaskSnapshot {
        if (handle == null || handle.isBlank()) {
            throw new IllegalArgumentException("Task handle must not be blank");
        }
        Objects.requireNonNull(tool, "tool");
        Objects.requireNonNull(status, "status");
        input = Map.copyOf(Objects.requireNonNull(input, "input"));
        output = output == null ? null : Map.copyOf(output);
        error = error == null ? null : Map.copyOf(error);
        if (attempt < 1 || maxAttempts < 1 || attempt > maxAttempts) {
            throw new IllegalArgumentException("Task attempts must satisfy 1 <= attempt <= maxAttempts");
        }
    }
}
