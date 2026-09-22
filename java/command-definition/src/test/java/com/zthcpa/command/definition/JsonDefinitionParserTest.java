package com.zthcpa.command.definition;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKind;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JsonDefinitionParserTest {
    private final JsonDefinitionParser parser = new JsonDefinitionParser(new ObjectMapper());

    @Test
    void parsesCommonDefinitionEnvelope() {
        DefinitionDocument definition = parser.parse(input("""
                {
                  "schema_version": 1,
                  "kind": "workflow",
                  "id": "ocr.extract-document",
                  "version": 1,
                  "status": "active",
                  "title": "OCR document"
                }
                """), "workflow.json");

        assertEquals(DefinitionKind.WORKFLOW, definition.key().kind());
        assertEquals("ocr.extract-document", definition.key().id());
        assertEquals("OCR document", definition.content().get("title"));
    }

    @Test
    void rejectsMissingAndInvalidEnvelopeFields() {
        DefinitionValidationException exception = assertThrows(
                DefinitionValidationException.class,
                () -> parser.parse(input("{\"kind\":\"workflow\",\"version\":0}"), "invalid.json")
        );

        assertEquals(4, exception.errors().size());
    }

    private ByteArrayInputStream input(String value) {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }
}
