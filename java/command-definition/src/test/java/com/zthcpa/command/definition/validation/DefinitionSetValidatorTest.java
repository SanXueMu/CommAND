package com.zthcpa.command.definition.validation;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DefinitionSetValidatorTest {
    private final DefinitionSetValidator validator = new DefinitionSetValidator();

    @Test
    void acceptsMultipleVersionsWithOneActiveDefinition() {
        assertDoesNotThrow(() -> validator.validate(List.of(
                definition(1, DefinitionStatus.DEPRECATED),
                definition(2, DefinitionStatus.ACTIVE)
        )));
    }

    @Test
    void rejectsMultipleActiveVersions() {
        assertThrows(DefinitionValidationException.class, () -> validator.validate(List.of(
                definition(1, DefinitionStatus.ACTIVE),
                definition(2, DefinitionStatus.ACTIVE)
        )));
    }

    private DefinitionDocument definition(int version, DefinitionStatus status) {
        return new DefinitionDocument(
                new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", version),
                1,
                status,
                Map.of("version", version),
                "0".repeat(64),
                "test"
        );
    }
}
