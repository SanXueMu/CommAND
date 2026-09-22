package com.zthcpa.command.catalog;

import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.contract.ToolNotFoundException;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class InMemoryToolCatalog implements ToolCatalog {
    private final Map<ToolKey, ToolDescriptor> tools;

    public InMemoryToolCatalog(List<ToolDescriptor> descriptors) {
        Map<ToolKey, ToolDescriptor> byKey = new LinkedHashMap<>();
        for (ToolDescriptor descriptor : descriptors) {
            if (byKey.put(descriptor.key(), descriptor) != null) {
                throw new IllegalArgumentException("Duplicate tool: " + descriptor.key());
            }
        }
        tools = Map.copyOf(byKey);
    }

    @Override
    public ToolDescriptor get(ToolKey key) {
        ToolDescriptor descriptor = tools.get(key);
        if (descriptor == null) {
            throw new ToolNotFoundException("Tool not found: " + key);
        }
        return descriptor;
    }

    @Override
    public List<ToolDescriptor> list() {
        return tools.values().stream()
                .sorted(Comparator.comparing((ToolDescriptor tool) -> tool.key().id())
                        .thenComparingInt(tool -> tool.key().version()))
                .toList();
    }
}
