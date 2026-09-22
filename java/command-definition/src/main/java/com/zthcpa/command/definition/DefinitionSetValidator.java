package com.zthcpa.command.definition;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DefinitionSetValidator {
    public void validate(List<DefinitionDocument> definitions) {
        List<String> errors = new ArrayList<>();
        Set<DefinitionKey> versions = new HashSet<>();
        Set<ActiveKey> activeDefinitions = new HashSet<>();

        for (DefinitionDocument definition : definitions) {
            if (!versions.add(definition.key())) {
                errors.add("Duplicate definition version: " + definition.key());
            }
            if (definition.status() == DefinitionStatus.ACTIVE) {
                ActiveKey activeKey = new ActiveKey(definition.key().kind(), definition.key().id());
                if (!activeDefinitions.add(activeKey)) {
                    errors.add("Multiple active definitions: " + activeKey);
                }
            }
        }

        if (!errors.isEmpty()) {
            throw new DefinitionValidationException(errors);
        }
    }

    private record ActiveKey(DefinitionKind kind, String id) { }
}
