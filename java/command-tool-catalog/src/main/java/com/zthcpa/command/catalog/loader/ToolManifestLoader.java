package com.zthcpa.command.catalog.loader;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.catalog.InMemoryToolCatalog;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.contract.RuntimeKind;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Loads executable-tool descriptions without resolving or instantiating implementations. */
public final class ToolManifestLoader {
    private final ClassLoader classLoader;
    private final ObjectMapper objectMapper;

    public ToolManifestLoader(ClassLoader classLoader, ObjectMapper objectMapper) {
        this.classLoader = classLoader;
        this.objectMapper = objectMapper;
    }

    public ToolCatalog load(String indexResource) {
        List<ToolDescriptor> descriptors = new ArrayList<>();
        try (InputStream index = resource(indexResource)) {
            if (index == null) {
                throw new IllegalArgumentException("Tool manifest index does not exist: " + indexResource);
            }
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(index, StandardCharsets.UTF_8))) {
                for (String line : reader.lines().map(String::trim)
                        .filter(value -> !value.isEmpty() && !value.startsWith("#")).toList()) {
                    descriptors.add(parse(line));
                }
            }
        } catch (IOException exception) {
            throw new IllegalArgumentException("Failed to read tool manifest index: " + indexResource, exception);
        }
        return new InMemoryToolCatalog(descriptors);
    }

    private ToolDescriptor parse(String resource) {
        try (InputStream input = resource(resource)) {
            if (input == null) {
                throw new IllegalArgumentException("Tool manifest does not exist: " + resource);
            }
            JsonNode root = objectMapper.readTree(input);
            if (!"tool".equals(text(root, "kind"))) {
                throw new IllegalArgumentException("Manifest is not a tool: " + resource);
            }
            ToolKey key = new ToolKey(text(root, "id"), positive(root, "version"));
            RuntimeKind runtimeKind = RuntimeKind.fromValue(runtime(root));
            Map<String, Object> manifest = objectMapper.convertValue(root, Map.class);
            return new ToolDescriptor(key, runtimeKind, text(root, "status"), manifest);
        } catch (IOException exception) {
            throw new IllegalArgumentException("Failed to read tool manifest: " + resource, exception);
        }
    }

    private InputStream resource(String name) {
        return classLoader.getResourceAsStream(name);
    }

    private static String runtime(JsonNode root) {
        String value = text(root, "runtime");
        return switch (value) {
            case "java" -> RuntimeKind.INPROC.value();
            default -> value;
        };
    }

    private static String text(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Tool manifest field must be a non-blank string: " + field);
        }
        return value.textValue();
    }

    private static int positive(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.canConvertToInt() || value.intValue() < 1) {
            throw new IllegalArgumentException("Tool manifest field must be positive: " + field);
        }
        return value.intValue();
    }
}
