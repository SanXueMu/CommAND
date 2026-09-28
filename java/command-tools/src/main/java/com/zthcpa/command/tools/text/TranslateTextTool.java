package com.zthcpa.command.tools.text;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.llm.LlmClient;
import com.zthcpa.command.tools.llm.LlmRequest;
import com.zthcpa.command.tools.llm.LlmResponse;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Reusable translation capability. Workflow-specific routing stays outside this Tool. */
public final class TranslateTextTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("text.translate", 1);
    private final LlmClient client;

    public TranslateTextTool(LlmClient client) {
        this.client = client;
    }

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        String text = text(input, "text");
        String target = text(input, "target_lang");
        String source = optionalText(input.get("source_lang"), "auto");
        String model = text(input, "model");
        String glossary = optionalText(input.get("glossary"), "");
        String instruction = optionalText(input.get("instruction"), "");

        progress.emit(Map.of("phase", "preparing", "source_lang", source, "target_lang", target));
        String system = "You are a professional translator. Translate faithfully into the target language. "
                + "Preserve placeholders, numbers, markup, line breaks, and paragraph structure. "
                + "Return only the translation without commentary.";
        String user = "Source language: " + source + "\nTarget language: " + target
                + (glossary.isBlank() ? "" : "\nGlossary:\n" + glossary)
                + (instruction.isBlank() ? "" : "\nAdditional instruction:\n" + instruction)
                + "\n\nText to translate:\n" + text;

        progress.emit(Map.of("phase", "translating", "model", model));
        LlmResponse response = client.complete(new LlmRequest(
                model,
                List.of(new LlmRequest.Message("system", system), new LlmRequest.Message("user", user)),
                0.2,
                null,
                false
        ));
        progress.emit(Map.of("phase", "completed", "model", response.model()));

        Map<String, Object> output = new LinkedHashMap<>();
        output.put("translation", response.content());
        output.put("source_lang", source);
        output.put("target_lang", target);
        output.put("model", response.model());
        output.put("usage", response.usage());
        return Map.copyOf(output);
    }

    private static String text(Map<String, Object> input, String key) {
        String value = optionalText(input.get(key), "");
        if (value.isBlank()) {
            throw new IllegalArgumentException(key + " must not be blank");
        }
        return value;
    }

    private static String optionalText(Object value, String fallback) {
        return value instanceof String text ? text : fallback;
    }
}
