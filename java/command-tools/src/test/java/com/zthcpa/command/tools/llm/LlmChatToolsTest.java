package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LlmChatToolsTest {
    @Test
    void completesArbitraryChatWithoutBusinessSpecificLogic() {
        RecordingClient client = new RecordingClient(new LlmResponse(
                "answer", "model-a", Map.of("total_tokens", 7)
        ));
        var tool = new LlmChatCompleteTool(client, new ObjectMapper());
        List<Map<String, Object>> events = new ArrayList<>();

        Map<String, Object> output = tool.execute(Map.of(
                "model", "model-a",
                "messages", List.of(
                        Map.of("role", "system", "content", "Follow instructions"),
                        Map.of("role", "user", "content", "Question")
                ),
                "temperature", 0.2,
                "max_tokens", 200
        ), events::add);

        assertEquals("answer", output.get("content"));
        assertEquals("model-a", output.get("model"));
        assertFalse(client.request.jsonObject());
        assertEquals(2, client.request.messages().size());
        assertEquals(List.of("requesting", "completed"), events.stream()
                .map(event -> String.valueOf(event.get("phase")))
                .toList());
    }

    @Test
    void completesAndParsesJsonObject() {
        RecordingClient client = new RecordingClient(new LlmResponse(
                "{\"category\":\"audit\",\"confidence\":0.9}",
                "model-json",
                Map.of()
        ));
        var tool = new LlmChatCompleteJsonTool(client, new ObjectMapper());

        Map<String, Object> output = tool.execute(Map.of(
                "model", "model-json",
                "messages", List.of(Map.of("role", "user", "content", "Classify"))
        ), event -> { });

        assertTrue(client.request.jsonObject());
        assertEquals(Map.of("category", "audit", "confidence", 0.9), output.get("json"));
    }

    private static final class RecordingClient implements LlmClient {
        private final LlmResponse response;
        private LlmRequest request;

        private RecordingClient(LlmResponse response) {
            this.response = response;
        }

        @Override
        public LlmResponse complete(LlmRequest request) {
            this.request = request;
            return response;
        }
    }
}
