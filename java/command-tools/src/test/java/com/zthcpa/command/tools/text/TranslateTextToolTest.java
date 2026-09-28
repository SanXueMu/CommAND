package com.zthcpa.command.tools.text;

import com.zthcpa.command.tools.llm.LlmClient;
import com.zthcpa.command.tools.llm.LlmRequest;
import com.zthcpa.command.tools.llm.LlmResponse;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TranslateTextToolTest {
    @Test
    void buildsReusableTranslationRequestAndReturnsStructuredOutput() {
        RecordingClient client = new RecordingClient(new LlmResponse(
                "你好，世界", "model-a", Map.of("total_tokens", 8)
        ));
        TranslateTextTool tool = new TranslateTextTool(client);
        List<Map<String, Object>> events = new ArrayList<>();

        Map<String, Object> output = tool.execute(Map.of(
                "text", "Hello, world",
                "source_lang", "English",
                "target_lang", "Chinese",
                "model", "model-a",
                "glossary", "world => 世界",
                "instruction", "Preserve punctuation"
        ), events::add);

        assertEquals("你好，世界", output.get("translation"));
        assertEquals("Chinese", output.get("target_lang"));
        assertEquals("model-a", output.get("model"));
        assertEquals(List.of("preparing", "translating", "completed"),
                events.stream().map(event -> String.valueOf(event.get("phase")).replace("", "")).toList());
        String prompt = client.request.messages().get(1).content();
        assertTrue(prompt.contains("Source language: English"));
        assertTrue(prompt.contains("world => 世界"));
        assertTrue(prompt.contains("Preserve punctuation"));
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
