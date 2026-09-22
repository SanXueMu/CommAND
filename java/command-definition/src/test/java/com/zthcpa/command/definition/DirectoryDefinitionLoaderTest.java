package com.zthcpa.command.definition;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DirectoryDefinitionLoaderTest {
    @TempDir
    Path tempDir;

    @Test
    void loadsJsonFilesRecursivelyInStableOrder() throws IOException {
        Files.createDirectories(tempDir.resolve("nested"));
        Files.writeString(tempDir.resolve("nested/b.json"), definition("b.workflow"));
        Files.writeString(tempDir.resolve("a.json"), definition("a.workflow"));
        Files.writeString(tempDir.resolve("ignored.txt"), "ignored");

        DirectoryDefinitionLoader loader = new DirectoryDefinitionLoader(
                tempDir,
                new JsonDefinitionParser(new ObjectMapper())
        );

        assertEquals(
                java.util.List.of("a.workflow", "b.workflow"),
                loader.load().stream().map(value -> value.key().id()).toList()
        );
    }

    @Test
    void rejectsMissingDirectory() {
        DirectoryDefinitionLoader loader = new DirectoryDefinitionLoader(
                tempDir.resolve("missing"),
                new JsonDefinitionParser(new ObjectMapper())
        );

        assertThrows(DefinitionValidationException.class, loader::load);
    }

    private String definition(String id) {
        return """
                {"schema_version":1,"kind":"workflow","id":"%s",
                 "version":1,"status":"active"}
                """.formatted(id);
    }
}
