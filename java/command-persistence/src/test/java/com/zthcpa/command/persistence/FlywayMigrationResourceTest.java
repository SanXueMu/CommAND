package com.zthcpa.command.persistence;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlywayMigrationResourceTest {
    private static final List<String> MIGRATIONS = List.of(
            "db/migration/V23__add_command_definitions.sql",
            "db/migration/V24__add_command_definition_aliases.sql",
            "db/migration/V25__add_run_definition_snapshots.sql"
    );

    @Test
    void packagesMigrationsAfterPythonBaselineTwentyTwo() throws IOException {
        for (String migration : MIGRATIONS) {
            assertNotNull(resource(migration), migration);
        }

        assertTrue(text(MIGRATIONS.get(0)).contains("CREATE TABLE command_definitions"));
        assertTrue(text(MIGRATIONS.get(1)).contains("CREATE TABLE command_definition_aliases"));
        assertTrue(text(MIGRATIONS.get(2)).contains("CREATE TABLE run_definition_snapshots"));
    }

    private InputStream resource(String path) {
        return getClass().getClassLoader().getResourceAsStream(path);
    }

    private String text(String path) throws IOException {
        try (InputStream stream = resource(path)) {
            assertNotNull(stream, path);
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
