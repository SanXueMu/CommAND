package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;
import java.util.Map;

public final class CleanEventLocalOpsRunner {
    private static final String RUN_ID = "clean-event-selftest-run";
    private static final String STEP_ID = "clean-event-selftest-step";
    private static final String TASK_ID = "clean-event-selftest-task";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new JdbcCleanEventRepository(jdbc, new ObjectMapper());
        try {
            createFixture(jdbc);
            long runFirst = repository.appendRunEvent(RUN_ID, STEP_ID, "run.started", "system",
                    Map.of("source", "selftest"));
            long taskFirst = repository.appendTaskEvent(TASK_ID, "task.claimed", Map.of("worker", "worker-a"));
            long runSecond = repository.appendRunEvent(RUN_ID, STEP_ID, "run.progress", "worker-a",
                    Map.of("percent", 50));

            List<CleanRunEvent> firstPage = repository.listRunEvents(RUN_ID, 0, 1);
            require(firstPage.size() == 1 && firstPage.get(0).id() == runFirst,
                    "run first page mismatch");
            List<CleanRunEvent> secondPage = repository.listRunEvents(RUN_ID, runFirst, 10);
            require(secondPage.size() == 1 && secondPage.get(0).id() == runSecond,
                    "run afterId page mismatch");
            List<CleanTaskEvent> taskEvents = repository.listTaskEvents(TASK_ID, taskFirst - 1, 10);
            require(taskEvents.size() == 1 && taskEvents.get(0).id() == taskFirst,
                    "task event mismatch");
            System.out.println("run events=2, task events=1, afterId pagination=ok");
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
        }
    }

    private static void createFixture(NamedParameterJdbcTemplate jdbc) {
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status)
                VALUES (?, 'test.workflow', 1, CAST(? AS jsonb), 'running')
                """, RUN_ID, "{}"
        );
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.run_steps (
                    id, run_id, step_index, step_key, definition_kind,
                    definition_id, definition_version, input, status
                ) VALUES (?, ?, 0, 'test.tool', 'tool', 'test.tool', 1,
                          CAST(? AS jsonb), 'running')
                """, STEP_ID, RUN_ID, "{}"
        );
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, status
                ) VALUES (?, ?, 1, 1, CAST(? AS jsonb), 'running')
                """, TASK_ID, STEP_ID, "{}"
        );
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

    private CleanEventLocalOpsRunner() {
    }
}
