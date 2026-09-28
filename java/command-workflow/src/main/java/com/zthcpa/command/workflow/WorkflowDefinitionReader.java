package com.zthcpa.command.workflow;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.ToolKey;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class WorkflowDefinitionReader {
    public WorkflowDefinition readWorkflow(DefinitionDocument document) {
        requireKind(document, DefinitionKind.WORKFLOW);
        Map<?, ?> pipelineRef = objectValue(document.content(), "capability_pipeline_ref");
        return new WorkflowDefinition(
                document.key(),
                text(document.content(), "title"),
                reference(pipelineRef, DefinitionKind.CAPABILITY_PIPELINE),
                objectContent(document.content(), "input_schema"),
                objectContent(document.content(), "output")
        );
    }

    public CapabilityPipelineDefinition readPipeline(DefinitionDocument document) {
        requireKind(document, DefinitionKind.CAPABILITY_PIPELINE);
        Object rawSteps = document.content().get("steps");
        if (!(rawSteps instanceof List<?> steps)) {
            throw invalid(document, "steps must be an array");
        }

        List<CapabilityPipelineDefinition.PipelineStep> parsed = new ArrayList<>();
        Set<String> stepIds = new HashSet<>();
        for (Object rawStep : steps) {
            Map<?, ?> step = asObject(rawStep, document, "pipeline step");
            String id = text(step, "id", document);
            if (stepIds.contains(id)) {
                throw invalid(document, "duplicate pipeline step id: " + id);
            }
            Map<?, ?> reference = asObject(step.get("definition_ref"), document, "definition_ref");
            Map<String, Object> input = step.containsKey("input")
                    ? stepInput(step, "input", document)
                    : Map.of();
            validateInputReferences(input, stepIds, document);
            stepIds.add(id);
            parsed.add(new CapabilityPipelineDefinition.PipelineStep(
                    id,
                    reference(reference, null, document),
                    input
            ));
        }
        return new CapabilityPipelineDefinition(document.key(), text(document.content(), "title"), parsed);
    }

    private void validateInputReferences(Object value, Set<String> previousStepIds,
                                         DefinitionDocument owner) {
        if (value instanceof Map<?, ?> map) {
            map.values().forEach(item -> validateInputReferences(item, previousStepIds, owner));
            return;
        }
        if (value instanceof List<?> list) {
            list.forEach(item -> validateInputReferences(item, previousStepIds, owner));
            return;
        }
        if (!(value instanceof String reference) || !reference.startsWith("$")) {
            return;
        }
        String[] parts = reference.split("\\.", -1);
        if ("$run".equals(parts[0])) {
            if (parts.length < 2 || hasBlankPart(parts)) {
                throw invalid(owner, "invalid input reference: " + reference);
            }
            return;
        }
        if (!"$step".equals(parts[0]) || parts.length < 3 || hasBlankPart(parts)) {
            throw invalid(owner, "invalid input reference: " + reference);
        }
        if (!previousStepIds.contains(parts[1])) {
            throw invalid(owner, "step input references a non-previous step: " + reference);
        }
    }

    private boolean hasBlankPart(String[] parts) {
        for (String part : parts) {
            if (part.isBlank()) {
                return true;
            }
        }
        return false;
    }

    private DefinitionKey reference(Map<?, ?> value, DefinitionKind expectedKind) {
        DefinitionKind kind = DefinitionKind.fromValue(value.get("kind").toString());
        if (expectedKind != null && kind != expectedKind) {
            throw new IllegalArgumentException("Expected " + expectedKind + " but got " + kind);
        }
        return new DefinitionKey(kind, value.get("id").toString(), number(value.get("version")));
    }

    private DefinitionReference reference(Map<?, ?> value, DefinitionKind ignored, DefinitionDocument owner) {
        DefinitionKind kind = DefinitionKind.fromValue(value.get("kind").toString());
        String id = value.get("id").toString();
        int version = number(value.get("version"));
        if (kind == DefinitionKind.TOOL) {
            return DefinitionReference.tool(new ToolKey(id, version));
        }
        return DefinitionReference.definition(new DefinitionKey(kind, id, version));
    }

    private void requireKind(DefinitionDocument document, DefinitionKind expected) {
        if (document.key().kind() != expected) {
            throw invalid(document, "Expected " + expected + " but got " + document.key().kind());
        }
    }

    private String text(Map<?, ?> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(field + " must be a non-blank string");
        }
        return text;
    }

    private String text(Map<?, ?> value, String field, DefinitionDocument owner) {
        try {
            return text(value, field);
        } catch (IllegalArgumentException exception) {
            throw invalid(owner, exception.getMessage());
        }
    }

    private Map<?, ?> objectValue(Map<?, ?> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Map<?, ?> object)) {
            throw new IllegalArgumentException(field + " must be an object");
        }
        return object;
    }

    private Map<String, Object> objectContent(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Map<?, ?> object)) {
            throw new IllegalArgumentException(field + " must be an object");
        }
        return object.entrySet().stream().collect(java.util.stream.Collectors.toUnmodifiableMap(
                entry -> entry.getKey().toString(), Map.Entry::getValue
        ));
    }

    private Map<?, ?> asObject(Object value, DefinitionDocument owner, String field) {
        if (!(value instanceof Map<?, ?> object)) {
            throw invalid(owner, field + " must be an object");
        }
        return object;
    }

    private Map<String, Object> stepInput(Map<?, ?> value, String field, DefinitionDocument owner) {
        return objectContentFromStep(value, field);
    }

    private Map<String, Object> objectContentFromStep(Map<?, ?> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Map<?, ?> object)) {
            throw new IllegalArgumentException(field + " must be an object");
        }
        return object.entrySet().stream().collect(java.util.stream.Collectors.toUnmodifiableMap(
                entry -> entry.getKey().toString(), Map.Entry::getValue
        ));
    }

    private int number(Object value) {
        if (!(value instanceof Number number) || number.intValue() < 1) {
            throw new IllegalArgumentException("version must be a positive integer");
        }
        return number.intValue();
    }

    private IllegalArgumentException invalid(DefinitionDocument document, String message) {
        return new IllegalArgumentException(document.key() + ": " + message);
    }
}
