package com.zthcpa.command.definition;

import com.zthcpa.command.contract.DefinitionDocument;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class ClasspathDefinitionLoader implements DefinitionLoader {
    private final ClassLoader classLoader;
    private final String indexResource;
    private final JsonDefinitionParser parser;

    public ClasspathDefinitionLoader(ClassLoader classLoader, String indexResource, JsonDefinitionParser parser) {
        this.classLoader = classLoader;
        this.indexResource = indexResource;
        this.parser = parser;
    }

    @Override
    public List<DefinitionDocument> load() {
        try (InputStream index = classLoader.getResourceAsStream(indexResource)) {
            if (index == null) {
                throw new DefinitionValidationException(List.of(
                        "Definition index does not exist: " + indexResource
                ));
            }
            List<String> resources = readResources(index);
            List<DefinitionDocument> definitions = new ArrayList<>();
            for (String resource : resources) {
                try (InputStream definition = classLoader.getResourceAsStream(resource)) {
                    if (definition == null) {
                        throw new DefinitionValidationException(List.of(
                                "Definition resource does not exist: " + resource
                        ));
                    }
                    definitions.add(parser.parse(definition, resource));
                }
            }
            return List.copyOf(definitions);
        } catch (IOException exception) {
            throw new DefinitionValidationException(List.of(
                    "Failed to read definition index " + indexResource + ": " + exception.getMessage()
            ));
        }
    }

    private List<String> readResources(InputStream index) throws IOException {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(index, StandardCharsets.UTF_8))) {
            return reader.lines()
                    .map(String::trim)
                    .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                    .sorted(Comparator.naturalOrder())
                    .toList();
        }
    }
}
