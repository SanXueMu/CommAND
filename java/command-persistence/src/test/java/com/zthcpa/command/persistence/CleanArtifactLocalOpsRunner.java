package com.zthcpa.command.persistence;

import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanArtifactLocalOpsRunner {
    private static final String RUN_ID = "clean-artifact-selftest-run";
    private static final String STEP_ID = "clean-artifact-selftest-step";
    private static final String ARTIFACT_ID = "clean-artifact-selftest-artifact";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new JdbcCleanArtifactRepository(jdbc, new com.fasterxml.jackson.databind.ObjectMapper());
        try {
            createFixture(jdbc);
            var artifact = new CleanArtifact(
                    ARTIFACT_ID, RUN_ID, STEP_ID, "translated_document",
                    "runs/clean-artifact-selftest/output.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    2048L, "a".repeat(64), Map.of("language", "zh") , null
            );
            require(repository.register(artifact), "artifact must register");
            require(!repository.register(artifact), "duplicate artifact must be ignored");
            require(repository.get(ARTIFACT_ID) != null, "artifact detail expected");
            require(repository.listByRun(RUN_ID, 0, 10).size() == 1, "run artifact expected");
            require(repository.listByStep(STEP_ID, 0, 10).size() == 1, "step artifact expected");
            require(repository.delete(ARTIFACT_ID), "artifact delete expected");
            require(repository.get(ARTIFACT_ID) == null, "artifact must be deleted");
            repository.register(artifact);
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
            long remaining = jdbc.getJdbcTemplate().queryForObject(
                    "SELECT count(*) FROM command_runtime.artifacts WHERE id = ?", Long.class, ARTIFACT_ID
            );
            System.out.println("registered=1, duplicate=false, run/step queries=ok, cascade_remaining=" + remaining);
            require(remaining == 0, "artifact must cascade with run");
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
        }
    }

    private static void createFixture(NamedParameterJdbcTemplate jdbc) {
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status)
                VALUES (?, 'test.workflow', 1, CAST(? AS jsonb), 'running')
                """, RUN_ID, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.run_steps (
                    id, run_id, step_index, step_key, definition_kind,
                    definition_id, definition_version, input, status
                ) VALUES (?, ?, 0, 'artifact-tool', 'tool', 'artifact-tool', 1,
                          CAST(? AS jsonb), 'running')
                """, STEP_ID, RUN_ID, "{}");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must be provided");
        }
        return value;
    }

    private CleanArtifactLocalOpsRunner() {
    }
}
