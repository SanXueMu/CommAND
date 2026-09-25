package com.zthcpa.command.tools.spi;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Immutable lookup boundary for Java in-process tools. */
public final class JavaToolRegistry {
    private final Map<Key, JavaTool> tools;

    public JavaToolRegistry(List<JavaTool> registeredTools) {
        Map<Key, JavaTool> values = new LinkedHashMap<>();
        for (JavaTool tool : registeredTools) {
            Key key = new Key(tool.id(), tool.version());
            if (values.put(key, tool) != null) {
                throw new IllegalArgumentException("Duplicate Java tool: " + key);
            }
        }
        tools = Map.copyOf(values);
    }

    public JavaTool get(String id, int version) {
        JavaTool tool = tools.get(new Key(id, version));
        if (tool == null) {
            throw new IllegalArgumentException("Java tool not registered: " + id + "/v" + version);
        }
        return tool;
    }

    public boolean contains(String id, int version) {
        return tools.containsKey(new Key(id, version));
    }

    public List<JavaTool> list() {
        return tools.values().stream()
                .sorted(java.util.Comparator.comparing(JavaTool::id).thenComparingInt(JavaTool::version))
                .toList();
    }

    private record Key(String id, int version) { }
}
