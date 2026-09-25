package com.zthcpa.command.tools.llm;

import java.util.Map;

public record LlmResponse(String content, String model, Map<String, Object> usage) {
    public LlmResponse {
        if (content == null) {
            throw new IllegalArgumentException("content must not be null");
        }
        if (model == null || model.isBlank()) {
            throw new IllegalArgumentException("model must not be blank");
        }
        usage = usage == null ? Map.of() : Map.copyOf(usage);
    }
}
