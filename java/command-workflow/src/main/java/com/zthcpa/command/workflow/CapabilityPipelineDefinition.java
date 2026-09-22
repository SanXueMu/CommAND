package com.zthcpa.command.workflow;

import com.zthcpa.command.contract.DefinitionKey;

import java.util.List;
import java.util.Objects;

public record CapabilityPipelineDefinition(
        DefinitionKey key,
        String title,
        List<PipelineStep> steps
) {
    public CapabilityPipelineDefinition {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(title, "title");
        if (title.isBlank()) {
            throw new IllegalArgumentException("Pipeline title must not be blank");
        }
        steps = List.copyOf(Objects.requireNonNull(steps, "steps"));
        if (steps.isEmpty()) {
            throw new IllegalArgumentException("Pipeline must contain at least one step");
        }
    }

    public record PipelineStep(String id, DefinitionReference reference) {
        public PipelineStep {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Pipeline step id must not be blank");
            }
            Objects.requireNonNull(reference, "reference");
        }
    }
}
