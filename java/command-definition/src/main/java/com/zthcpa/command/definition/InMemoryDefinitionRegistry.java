package com.zthcpa.command.definition;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionNotFoundException;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.DefinitionStatus;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class InMemoryDefinitionRegistry implements DefinitionRegistry {
    private final Map<DefinitionKey, DefinitionDocument> byKey;
    private final Map<ActiveKey, DefinitionDocument> active;

    public InMemoryDefinitionRegistry(
            List<DefinitionDocument> definitions,
            DefinitionSetValidator validator
    ) {
        validator.validate(definitions);
        Map<DefinitionKey, DefinitionDocument> definitionsByKey = new LinkedHashMap<>();
        Map<ActiveKey, DefinitionDocument> activeDefinitions = new LinkedHashMap<>();
        for (DefinitionDocument definition : definitions) {
            definitionsByKey.put(definition.key(), definition);
            if (definition.status() == DefinitionStatus.ACTIVE) {
                activeDefinitions.put(
                        new ActiveKey(definition.key().kind(), definition.key().id()),
                        definition
                );
            }
        }
        this.byKey = Map.copyOf(definitionsByKey);
        this.active = Map.copyOf(activeDefinitions);
    }

    @Override
    public DefinitionDocument get(DefinitionKey key) {
        DefinitionDocument definition = byKey.get(key);
        if (definition == null) {
            throw new DefinitionNotFoundException("Definition not found: " + key);
        }
        return definition;
    }

    @Override
    public DefinitionDocument getActive(DefinitionKind kind, String id) {
        DefinitionDocument definition = active.get(new ActiveKey(kind, id));
        if (definition == null) {
            throw new DefinitionNotFoundException("Active definition not found: " + kind + "/" + id);
        }
        return definition;
    }

    @Override
    public List<DefinitionDocument> list(DefinitionKind kind) {
        return byKey.values().stream()
                .filter(definition -> definition.key().kind() == kind)
                .sorted(Comparator
                        .comparing((DefinitionDocument definition) -> definition.key().id())
                        .thenComparingInt(definition -> definition.key().version()))
                .toList();
    }

    private record ActiveKey(DefinitionKind kind, String id) { }
}
