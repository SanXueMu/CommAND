package com.zthcpa.command.tools.llm;

import java.util.List;

public record LlmRequest(
        String model,
        List<Message> messages,
        Double temperature,
        Integer maxTokens,
        boolean jsonObject
) {
    public LlmRequest {
        if (model == null || model.isBlank()) {
            throw new IllegalArgumentException("model must not be blank");
        }
        messages = List.copyOf(messages);
        if (messages.isEmpty()) {
            throw new IllegalArgumentException("messages must not be empty");
        }
    }

    public record Message(String role, String content) {
        public Message {
            if (role == null || role.isBlank()) {
                throw new IllegalArgumentException("message role must not be blank");
            }
            if (content == null) {
                throw new IllegalArgumentException("message content must not be null");
            }
        }
    }
}
