package com.zthcpa.command.tools;

import java.util.List;
import java.util.Map;

public record TranslationBatch(
        List<TranslationItem> items,
        Usage usage
) {
    public TranslationBatch {
        items = List.copyOf(items);
        usage = usage == null ? new Usage(0, 0) : usage;
    }

    public record TranslationItem(String source, String translated, String status, String model) { }

    public record Usage(int promptTokens, int completionTokens) {
        public Map<String, Object> asMap() {
            return Map.of("prompt_tokens", promptTokens, "completion_tokens", completionTokens);
        }
    }
}
