package com.zthcpa.command.workflow;

import com.zthcpa.command.contract.DefinitionKey;

import java.util.Map;
import java.util.Objects;

public record WorkflowDefinition(
        DefinitionKey key,
        String title,
        DefinitionKey capabilityPipeline,
        Map<String, Object> inputSchema,
        Map<String, Object> output
) {
    public WorkflowDefinition {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(capabilityPipeline, "capabilityPipeline");
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Workflow title must not be blank");
        }
        inputSchema = Map.copyOf(Objects.requireNonNull(inputSchema, "inputSchema"));
        output = Map.copyOf(Objects.requireNonNull(output, "output"));
    }
}
