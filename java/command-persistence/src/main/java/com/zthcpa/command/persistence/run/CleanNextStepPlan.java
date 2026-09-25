package com.zthcpa.command.persistence.run;

import com.zthcpa.command.contract.DefinitionKey;

import java.util.Map;
import java.util.Objects;

public record CleanNextStepPlan(
        String stepId,
        int stepIndex,
        String stepKey,
        DefinitionKey tool,
        Map<String, Object> input,
        String taskId,
        int maxAttempts
) {
    public CleanNextStepPlan {
        require(stepId, "Step id");
        require(stepKey, "Step key");
        Objects.requireNonNull(tool, "tool");
        input = Map.copyOf(Objects.requireNonNull(input, "input"));
        require(taskId, "Task id");
        if (stepIndex < 0 || maxAttempts < 1) {
            throw new IllegalArgumentException("Invalid next step position or retry limit");
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
