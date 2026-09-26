package com.zthcpa.command.definition.loader;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.definition.validation.DefinitionValidationException;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class DirectoryDefinitionLoader implements DefinitionLoader {
    private final Path root;
    private final JsonDefinitionParser parser;

    public DirectoryDefinitionLoader(Path root, JsonDefinitionParser parser) {
        this.root = root;
        this.parser = parser;
    }

    @Override
    public List<DefinitionDocument> load() {
        if (!Files.isDirectory(root)) {
            throw new DefinitionValidationException(List.of("Definition directory does not exist: " + root));
        }

        List<Path> files;
        try (Stream<Path> paths = Files.walk(root)) {
            files = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(Path::toString))
                    .toList();
        } catch (IOException exception) {
            throw new DefinitionValidationException(List.of(
                    "Failed to list definition directory " + root + ": " + exception.getMessage()
            ));
        }

        List<DefinitionDocument> definitions = new ArrayList<>();
        for (Path file : files) {
            try (InputStream input = Files.newInputStream(file)) {
                definitions.add(parser.parse(input, root.relativize(file).toString()));
            } catch (IOException exception) {
                throw new DefinitionValidationException(List.of(
                        "Failed to read definition " + file + ": " + exception.getMessage()
                ));
            }
        }
        return List.copyOf(definitions);
    }
}
