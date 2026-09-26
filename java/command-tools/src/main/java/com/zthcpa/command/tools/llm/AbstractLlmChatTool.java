package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

abstract class AbstractLlmChatTool implements JavaTool {
    private final LlmClient client;
    private final ObjectMapper mapper;
    private final boolean jsonObject;

    AbstractLlmChatTool(LlmClient client, ObjectMapper mapper, boolean jsonObject) {
        this.client = client;
        this.mapper = mapper;
        this.jsonObject = jsonObject;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        LlmRequest request = new LlmRequest(
                requiredText(input.get("model"), "model"),
                messages(input.get("messages")),
                number(input.get("temperature")),
                integer(input.get("max_tokens")),
                jsonObject
        );
        progress.emit(Map.of("phase", "requesting", "model", request.model()));
        LlmResponse response = client.complete(request);
        progress.emit(Map.of("phase", "completed", "model", response.model()));

        Map<String, Object> output = new LinkedHashMap<>();
        output.put(jsonObject ? "json" : "content", jsonObject ? parseJson(response.content()) : response.content());
        output.put("model", response.model());
        output.put("usage", response.usage());
        return Map.copyOf(output);
    }

    private List<LlmRequest.Message> messages(Object value) {
        if (!(value instanceof List<?> values) || values.isEmpty()) {
            throw new LlmToolException("messages must be a non-empty array");
        }
        List<LlmRequest.Message> messages = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof Map<?, ?> message)) {
                throw new LlmToolException("each message must be an object");
            }
            messages.add(new LlmRequest.Message(
                    requiredText(message.get("role"), "message.role"),
                    requiredText(message.get("content"), "message.content")
            ));
        }
        return List.copyOf(messages);
    }

    private Map<String, Object> parseJson(String content) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> value = mapper.readValue(content, Map.class);
            return Map.copyOf(value);
        } catch (JsonProcessingException exception) {
            throw new LlmToolException("LLM response is not a JSON object", exception);
        }
    }

    private static String requiredText(Object value, String name) {
        if (!(value instanceof String text) || text.isBlank()) {
            throw new LlmToolException(name + " must not be blank");
        }
        return text;
    }

    private static Double number(Object value) {
        if (value == null) {
            return null;
        }
        if (!(value instanceof Number number)) {
            throw new LlmToolException("temperature must be numeric");
        }
        return number.doubleValue();
    }

    private static Integer integer(Object value) {
        if (value == null) {
            return null;
        }
        if (!(value instanceof Number number) || number.intValue() <= 0) {
            throw new LlmToolException("max_tokens must be a positive integer");
        }
        return number.intValue();
    }
}
