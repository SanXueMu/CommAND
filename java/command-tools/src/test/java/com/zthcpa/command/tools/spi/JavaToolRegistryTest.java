package com.zthcpa.command.tools.spi;

import com.zthcpa.command.contract.ToolKey;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JavaToolRegistryTest {
    @Test
    void resolvesToolsByStableIdAndVersion() {
        JavaTool tool = new JavaTool() {
            @Override public ToolKey key() { return new ToolKey("llm.chat.complete", 1); }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                return Map.of();
            }
        };

        JavaToolRegistry registry = new JavaToolRegistry(List.of(tool));

        assertEquals(tool, registry.get("llm.chat.complete", 1));
        assertThrows(IllegalArgumentException.class, () -> registry.get("llm.chat.complete", 2));
    }
}
