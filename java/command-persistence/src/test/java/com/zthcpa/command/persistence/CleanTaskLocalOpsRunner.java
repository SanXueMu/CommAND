package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanTaskLocalOpsRunner {
    private static final String RUN_ID = "clean-task-selftest-run";
    private static final String STEP_ID = "clean-task-selftest-step";
    private static final String TASK_ID = "clean-task-selftest-task";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        ObjectMapper mapper = new ObjectMapper();
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new JdbcCleanTaskRepository(jdbc, mapper);
        try {
            createFixture(jdbc);
            var firstClaim = repository.claimNext("worker-a")
                    .orElseThrow(() -> new IllegalStateException("Task was not claimed"));
            require(firstClaim.status() == TaskStatus.RUNNING, "first claim must be running");
            require(repository.heartbeat(TASK_ID, "worker-a"), "heartbeat must be accepted");
            require(repository.requeue(TASK_ID, "worker-a"), "requeue must be accepted");

            var secondClaim = repository.claimNext("worker-b")
                    .orElseThrow(() -> new IllegalStateException("Requeued task was not claimed"));
            require(secondClaim.attempt() == 2, "requeue must increment attempt");
            require(repository.finish(TASK_ID, "worker-b", TaskStatus.SUCCEEDED,
                    Map.of("ok", true), null), "finish must be accepted");
            require(!repository.heartbeat(TASK_ID, "worker-b"), "terminal task heartbeat must be rejected");
            System.out.println("claim=running, heartbeat=true, requeue=attempt2, finish=succeeded");
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
                          CAST(? AS jsonb), 'queued')
                """, STEP_ID, RUN_ID, "{}"
        );
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, status
                ) VALUES (?, ?, 1, 2, CAST(? AS jsonb), 'queued')
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

    private CleanTaskLocalOpsRunner() {
    }
}
