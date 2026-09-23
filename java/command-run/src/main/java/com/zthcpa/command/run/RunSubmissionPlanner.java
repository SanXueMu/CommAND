package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.DefinitionStatus;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public final class RunSubmissionPlanner {
    private final DefinitionRegistry definitions;
    private final Supplier<String> idGenerator;

    public RunSubmissionPlanner(DefinitionRegistry definitions, Supplier<String> idGenerator) {
        this.definitions = Objects.requireNonNull(definitions, "definitions");
        this.idGenerator = Objects.requireNonNull(idGenerator, "idGenerator");
    }

    public RunSubmissionPlan plan(String workflowId, Map<String, Object> input) {
        return plan(workflowId, null, input);
    }

    public RunSubmissionPlan plan(String workflowId, Integer workflowVersion, Map<String, Object> input) {
        if (workflowId == null || workflowId.isBlank()) {
            throw new RunSubmissionException("Workflow id must not be blank");
        }
        if (workflowVersion != null && workflowVersion < 1) {
            throw new RunSubmissionException("Workflow version must be positive");
        }
        Map<String, Object> runInput = Map.copyOf(Objects.requireNonNull(input, "input"));
        DefinitionDocument workflow = workflowVersion == null
                ? definitions.getActive(DefinitionKind.WORKFLOW, workflowId)
                : definitions.get(new DefinitionKey(DefinitionKind.WORKFLOW, workflowId, workflowVersion));
        if (workflow.status() != DefinitionStatus.ACTIVE) {
            throw new RunSubmissionException("Workflow definition is not active: " + workflow.key());
        }
        DefinitionKey pipelineKey = reference(workflow, "capability_pipeline_ref", DefinitionKind.CAPABILITY_PIPELINE);
        DefinitionDocument pipeline = definitions.get(pipelineKey);

        Object stepsValue = pipeline.content().get("steps");
        if (!(stepsValue instanceof List<?> steps) || steps.isEmpty()) {
            throw new RunSubmissionException("Capability pipeline has no steps: " + pipeline.key());
        }
        Object firstValue = steps.get(0);
        if (!(firstValue instanceof Map<?, ?> first)) {
            throw new RunSubmissionException("First pipeline step is not an object: " + pipeline.key());
        }
        Object referenceValue = first.get("definition_ref");
        DefinitionKey toolKey = reference(referenceValue, pipeline.key(), DefinitionKind.TOOL);

        String runId = idGenerator.get();
        String handle = idGenerator.get();
        if (runId == null || runId.isBlank() || handle == null || handle.isBlank()) {
            throw new RunSubmissionException("Id generator returned a blank identifier");
        }
        return new RunSubmissionPlan(
                runId,
                workflow.key(),
                runInput,
                List.of(workflow, pipeline),
                new RunSubmissionPlan.TaskPlan(handle, toolKey, runInput, 0, 1)
        );
    }

    public PipelineRunSubmissionPlan planPipeline(String workflowId, Map<String, Object> input) {
        return planPipeline(workflowId, null, input);
    }

    public PipelineRunSubmissionPlan planPipeline(
            String workflowId,
            Integer workflowVersion,
            Map<String, Object> input
    ) {
        RunSubmissionPlan first = plan(workflowId, workflowVersion, input);
        DefinitionDocument pipeline = definitions.get(
                reference(first.definitions().get(0), "capability_pipeline_ref", DefinitionKind.CAPABILITY_PIPELINE)
        );
        PipelineExecutionPlan execution = new PipelineExecutionPlanner(definitions)
                .plan(pipeline.key(), input);
        List<String> taskIds = execution.steps().stream()
                .map(step -> idGenerator.get())
                .toList();
        return new PipelineRunSubmissionPlan(
                first.runId(), first.workflow(), first.input(), first.definitions(), execution, taskIds
        );
    }

    private DefinitionKey reference(
            DefinitionDocument owner,
            String field,
            DefinitionKind expectedKind
    ) {
        return reference(owner.content().get(field), owner.key(), expectedKind);
    }

    private DefinitionKey reference(Object value, DefinitionKey owner, DefinitionKind expectedKind) {
        if (!(value instanceof Map<?, ?> values)) {
            throw new RunSubmissionException(owner + " has no valid " + expectedKind + " reference");
        }
        Object kind = values.get("kind");
        Object id = values.get("id");
        Object version = values.get("version");
        if (!(kind instanceof String kindValue)
                || !(id instanceof String idValue)
                || !(version instanceof Number versionValue)) {
            throw new RunSubmissionException(owner + " has an invalid definition reference");
        }
        DefinitionKind actualKind = DefinitionKind.fromValue(kindValue);
        if (actualKind != expectedKind) {
            throw new RunSubmissionException(owner + " references " + actualKind + ", expected " + expectedKind);
        }
        DefinitionKey key = new DefinitionKey(actualKind, idValue, versionValue.intValue());
        if (actualKind == DefinitionKind.TOOL) {
            return key;
        }
        DefinitionDocument referenced = definitions.get(key);
        if (referenced.status() != DefinitionStatus.ACTIVE) {
            throw new RunSubmissionException("Referenced definition is not active: " + key);
        }
        return key;
    }
}
