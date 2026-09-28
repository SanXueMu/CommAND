package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public record PipelineRunSubmissionPlan(
        String runId,
        DefinitionKey workflow,
        Map<String, Object> input,
        List<DefinitionDocument> definitions,
        PipelineExecutionPlan execution,
        List<String> taskIds
) {
    public PipelineRunSubmissionPlan {
        require(runId, "Run id");
        Objects.requireNonNull(workflow, "workflow");
        input = Map.copyOf(Objects.requireNonNull(input, "input"));
        definitions = List.copyOf(Objects.requireNonNull(definitions, "definitions"));
        Objects.requireNonNull(execution, "execution");
        taskIds = List.copyOf(Objects.requireNonNull(taskIds, "taskIds"));
        if (!execution.pipeline().equals(findPipeline(definitions))) {
            throw new IllegalArgumentException("Execution pipeline is not included in definitions");
        }
        if (taskIds.size() != execution.steps().size()) {
            throw new IllegalArgumentException("Task id count must match execution steps");
        }
        for (int index = 0; index < taskIds.size(); index++) {
            String expected = PipelineExecutionIdentifiers.taskId(runId, execution.steps().get(index).index());
            if (!expected.equals(taskIds.get(index))) {
                throw new IllegalArgumentException("Task id does not match the frozen execution identifier");
            }
        }
    }

    public String firstTaskId() {
        return taskIds.get(0);
    }

    private static DefinitionKey findPipeline(List<DefinitionDocument> definitions) {
        return definitions.stream()
                .map(DefinitionDocument::key)
                .filter(key -> key.kind() == com.zthcpa.command.contract.DefinitionKind.CAPABILITY_PIPELINE)
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Pipeline definition is required"));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
