package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public record RunSubmissionPlan(
        String runId,
        DefinitionKey workflow,
        Map<String, Object> input,
        List<DefinitionDocument> definitions,
        TaskPlan firstTask
) {
    public RunSubmissionPlan {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        Objects.requireNonNull(workflow, "workflow");
        input = Map.copyOf(Objects.requireNonNull(input, "input"));
        definitions = List.copyOf(Objects.requireNonNull(definitions, "definitions"));
        Objects.requireNonNull(firstTask, "firstTask");
    }

    public record TaskPlan(
            String handle,
            DefinitionKey tool,
            Map<String, Object> input,
            int stepIndex,
            int maxAttempts
    ) {
        public TaskPlan {
            if (handle == null || handle.isBlank()) {
                throw new IllegalArgumentException("Task handle must not be blank");
            }
            Objects.requireNonNull(tool, "tool");
            input = Map.copyOf(Objects.requireNonNull(input, "input"));
            if (stepIndex < 0 || maxAttempts < 1) {
                throw new IllegalArgumentException("Invalid task position or retry limit");
            }
        }
    }
}
