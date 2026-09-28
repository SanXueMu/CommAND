package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionKey;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public record PipelineExecutionPlan(
        DefinitionKey pipeline,
        List<StepPlan> steps
) {
    public PipelineExecutionPlan {
        Objects.requireNonNull(pipeline, "pipeline");
        steps = List.copyOf(Objects.requireNonNull(steps, "steps"));
        if (steps.isEmpty()) {
            throw new IllegalArgumentException("Execution plan must contain steps");
        }
    }

    public record StepPlan(
            int index,
            String id,
            DefinitionKey tool,
            Map<String, Object> input,
            Map<String, Object> inputTemplate,
            int maxAttempts
    ) {
        public StepPlan(int index, String id, DefinitionKey tool, Map<String, Object> input, int maxAttempts) {
            this(index, id, tool, input, input, maxAttempts);
        }

        public StepPlan {
            if (index < 0 || id == null || id.isBlank()) {
                throw new IllegalArgumentException("Invalid step index or id");
            }
            Objects.requireNonNull(tool, "tool");
            input = Map.copyOf(Objects.requireNonNull(input, "input"));
            inputTemplate = Map.copyOf(Objects.requireNonNull(inputTemplate, "inputTemplate"));
            if (maxAttempts < 1) {
                throw new IllegalArgumentException("Max attempts must be positive");
            }
        }
    }
}
