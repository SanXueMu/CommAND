package com.zthcpa.command.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;

final class PostgresJson {
    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {
    };

    private PostgresJson() {
    }

    static Map<String, Object> read(ObjectMapper mapper, String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return mapper.readValue(value, MAP_TYPE);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Invalid PostgreSQL JSONB value", exception);
        }
    }

    static String write(ObjectMapper mapper, Map<String, Object> value) {
        if (value == null) {
            return null;
        }
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Cannot serialize PostgreSQL JSONB value", exception);
        }
    }
}
