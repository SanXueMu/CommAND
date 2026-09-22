package com.zthcpa.command.definition;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class JsonDefinitionParser {
    private final ObjectMapper objectMapper;

    public JsonDefinitionParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public DefinitionDocument parse(InputStream input, String source) {
        try {
            JsonNode root = objectMapper.readTree(input);
            List<String> errors = validateEnvelope(root);
            if (!errors.isEmpty()) {
                throw new DefinitionValidationException(errors);
            }

            DefinitionKey key = new DefinitionKey(
                    DefinitionKind.fromValue(root.get("kind").textValue()),
                    root.get("id").textValue(),
                    root.get("version").intValue()
            );
            Map<String, Object> content = objectMapper.convertValue(
                    root, new TypeReference<Map<String, Object>>() { }
            );
            return new DefinitionDocument(
                    key,
                    root.get("schema_version").intValue(),
                    DefinitionStatus.fromValue(root.get("status").textValue()),
                    content,
                    source
            );
        } catch (DefinitionValidationException exception) {
            throw exception;
        } catch (IllegalArgumentException | IOException exception) {
            throw new DefinitionValidationException(List.of(source + ": " + exception.getMessage()));
        }
    }

    private List<String> validateEnvelope(JsonNode root) {
        List<String> errors = new ArrayList<>();
        if (!root.isObject()) {
            return List.of("Definition must be a JSON object");
        }
        requireText(root, "kind", errors);
        requireText(root, "id", errors);
        requirePositiveInteger(root, "version", errors);
        requirePositiveInteger(root, "schema_version", errors);
        requireText(root, "status", errors);
        return errors;
    }

    private void requireText(JsonNode root, String field, List<String> errors) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            errors.add(field + " must be a non-blank string");
        }
    }

    private void requirePositiveInteger(JsonNode root, String field, List<String> errors) {
        JsonNode value = root.get(field);
        if (value == null || !value.isIntegralNumber() || !value.canConvertToInt() || value.intValue() < 1) {
            errors.add(field + " must be a positive integer");
        }
    }
}
