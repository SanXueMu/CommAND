package com.zthcpa.command.definition.validation;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.definition.validation.DefinitionValidationException;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class DefinitionReferenceValidator {
    public void validate(List<DefinitionDocument> definitions) {
        Map<DefinitionKey, DefinitionDocument> byKey = new HashMap<>();
        for (DefinitionDocument definition : definitions) {
            byKey.put(definition.key(), definition);
        }

        List<String> errors = new ArrayList<>();
        for (DefinitionDocument definition : definitions) {
            if (definition.key().kind() == DefinitionKind.WORKFLOW) {
                validateReference(definition, definition.content().get("capability_pipeline_ref"),
                        DefinitionKind.CAPABILITY_PIPELINE, byKey, errors);
            }
            if (definition.key().kind() == DefinitionKind.WORKBENCH_VIEW) {
                validateReference(definition, definition.content().get("workflow_ref"),
                        DefinitionKind.WORKFLOW, byKey, errors);
            }
            if (definition.key().kind() == DefinitionKind.CAPABILITY_PIPELINE) {
                validatePipelineSteps(definition, byKey, errors);
            }
        }

        if (!errors.isEmpty()) {
            throw new DefinitionValidationException(errors);
        }
    }

    private void validatePipelineSteps(
            DefinitionDocument definition,
            Map<DefinitionKey, DefinitionDocument> byKey,
            List<String> errors
    ) {
        Object stepsValue = definition.content().get("steps");
        if (!(stepsValue instanceof List<?> steps)) {
            return;
        }
        for (Object step : steps) {
            if (step instanceof Map<?, ?> stepMap) {
                validateReference(definition, stepMap.get("definition_ref"), null, byKey, errors);
            }
        }
    }

    private void validateReference(
            DefinitionDocument owner,
            Object reference,
            DefinitionKind expectedKind,
            Map<DefinitionKey, DefinitionDocument> byKey,
            List<String> errors
    ) {
        if (reference == null) {
            return;
        }
        if (!(reference instanceof Map<?, ?> values)) {
            errors.add(owner.key() + " has a non-object definition reference");
            return;
        }
        Object kindValue = values.get("kind");
        Object idValue = values.get("id");
        Object versionValue = values.get("version");
        if (!(kindValue instanceof String kind)
                || !(idValue instanceof String id)
                || !(versionValue instanceof Number version)) {
            errors.add(owner.key() + " has an invalid definition reference");
            return;
        }

        DefinitionKind referencedKind;
        try {
            referencedKind = DefinitionKind.fromValue(kind);
        } catch (IllegalArgumentException exception) {
            errors.add(owner.key() + " references unknown kind: " + kind);
            return;
        }
        if (expectedKind != null && referencedKind != expectedKind) {
            errors.add(owner.key() + " references " + referencedKind + ", expected " + expectedKind);
            return;
        }
        if (referencedKind == DefinitionKind.TOOL) {
            return;
        }
        DefinitionKey key = new DefinitionKey(referencedKind, id, version.intValue());
        if (!byKey.containsKey(key)) {
            errors.add(owner.key() + " references missing definition: " + key);
        }
    }
}
