package com.zthcpa.command.definition;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionNotFoundException;
import com.zthcpa.command.contract.DefinitionStatus;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InMemoryDefinitionRegistryTest {
    @Test
    void resolvesExactAndActiveDefinitions() {
        DefinitionDocument oldDefinition = definition(1, DefinitionStatus.DEPRECATED);
        DefinitionDocument activeDefinition = definition(2, DefinitionStatus.ACTIVE);
        InMemoryDefinitionRegistry registry = new InMemoryDefinitionRegistry(
                List.of(oldDefinition, activeDefinition),
                new DefinitionSetValidator()
        );

        assertEquals(oldDefinition, registry.get(oldDefinition.key()));
        assertEquals(activeDefinition, registry.getActive(DefinitionKind.WORKFLOW, "ocr.extract-document"));
        assertEquals(List.of(oldDefinition, activeDefinition), registry.list(DefinitionKind.WORKFLOW));
    }

    @Test
    void rejectsMissingDefinition() {
        InMemoryDefinitionRegistry registry = new InMemoryDefinitionRegistry(
                List.of(definition(1, DefinitionStatus.ACTIVE)),
                new DefinitionSetValidator()
        );

        assertThrows(
                DefinitionNotFoundException.class,
                () -> registry.getActive(DefinitionKind.WORKFLOW, "missing")
        );
    }

    @Test
    void rejectsMissingNonToolReference() {
        DefinitionDocument workflow = new DefinitionDocument(
                new DefinitionKey(DefinitionKind.WORKFLOW, "missing-ref", 1),
                1,
                DefinitionStatus.ACTIVE,
                Map.of("capability_pipeline_ref", Map.of(
                        "kind", "capability_pipeline",
                        "id", "missing",
                        "version", 1
                )),
                "0".repeat(64),
                "test"
        );

        assertThrows(
                DefinitionValidationException.class,
                () -> new InMemoryDefinitionRegistry(List.of(workflow), new DefinitionSetValidator())
        );
    }

    private DefinitionDocument definition(int version, DefinitionStatus status) {
        return new DefinitionDocument(
                new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", version),
                1,
                status,
                Map.of("version", version),
                Integer.toString(version, 16).repeat(64),
                "test"
        );
    }
}
