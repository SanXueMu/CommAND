package com.zthcpa.command.tools.spi;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JavaToolRegistryTest {
    @Test
    void resolvesToolsByStableIdAndVersion() {
        JavaTool tool = new JavaTool() {
            @Override public String id() { return "llm.chat.complete"; }
            @Override public int version() { return 1; }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                return Map.of();
            }
        };

        JavaToolRegistry registry = new JavaToolRegistry(List.of(tool));

        assertEquals(tool, registry.get("llm.chat.complete", 1));
        assertThrows(IllegalArgumentException.class, () -> registry.get("llm.chat.complete", 2));
    }
}
