package com.zthcpa.command.persistence;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanMigrationResourceTest {
    @Test
    void definesIndependentRuntimeSchemaWithoutLegacyTables() throws IOException {
        String path = "db/clean-migration/V1__create_clean_command_schema.sql";
        try (InputStream stream = getClass().getClassLoader().getResourceAsStream(path)) {
            assertNotNull(stream);
            String sql = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(sql.contains("CREATE TABLE command_definitions"));
            assertTrue(sql.contains("CREATE TABLE runs"));
            assertTrue(sql.contains("CREATE TABLE run_steps"));
            assertTrue(sql.contains("CREATE TABLE task_executions"));
            assertTrue(sql.contains("CREATE TABLE run_events"));
            assertTrue(sql.contains("CREATE TABLE artifacts"));
            assertFalse(sql.contains("CREATE TABLE pipeline_runs"));
            assertFalse(sql.contains("CREATE TABLE tasks"));
            assertFalse(sql.contains("CREATE TABLE pipelines"));
        }
    }
}
