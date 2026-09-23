package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanRunStopLocalOpsRunner {
    public static void main(String[] args) {
        runCase("cancelled", TaskStatus.CANCELLED);
        runCase("interrupted", TaskStatus.INTERRUPTED);
    }

    private static void runCase(String suffix, TaskStatus status) {
        String runId = "clean-stop-selftest-" + suffix + "-run";
        String stepId = "clean-stop-selftest-" + suffix + "-step";
        String taskId = "clean-stop-selftest-" + suffix + "-task";

        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new CleanRunCompletionRepository(jdbc, new ObjectMapper(), dataSource);
        try {
            createFixture(jdbc, runId, stepId, taskId);
            require(repository.stopTask(taskId, "worker-a", status, Map.of("reason", suffix)),
                    "stop must succeed");
            require(!repository.stopTask(taskId, "worker-a", status, Map.of("reason", "duplicate")),
                    "duplicate stop must be ignored");
            Map<String, Object> result = jdbc.getJdbcTemplate().queryForMap("""
                    SELECT
                      (SELECT status FROM command_runtime.runs WHERE id = ?) AS run_status,
                      (SELECT status FROM command_runtime.run_steps WHERE id = ?) AS step_status,
                      (SELECT status FROM command_runtime.task_executions WHERE id = ?) AS task_status,
                      (SELECT count(*) FROM command_runtime.run_events WHERE run_id = ?) AS run_events,
                      (SELECT count(*) FROM command_runtime.task_events WHERE task_id = ?) AS task_events
                    """, runId, stepId, taskId, runId, taskId);
            System.out.println(suffix + "=" + result);
            require(suffix.equals(result.get("run_status")), "run state mismatch");
            require(suffix.equals(result.get("step_status")), "step state mismatch");
            require(suffix.equals(result.get("task_status")), "task state mismatch");
            require(((Number) result.get("run_events")).longValue() == 1, "run event mismatch");
            require(((Number) result.get("task_events")).longValue() == 1, "task event mismatch");
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }

    private static void createFixture(NamedParameterJdbcTemplate jdbc, String runId, String stepId, String taskId) {
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status)
                VALUES (?, 'test.workflow', 1, CAST(? AS jsonb), 'running')
                """, runId, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.run_steps (
                    id, run_id, step_index, step_key, definition_kind,
                    definition_id, definition_version, input, status
                ) VALUES (?, ?, 0, 'stoppable-tool', 'tool', 'stoppable-tool', 1,
                          CAST(? AS jsonb), 'running')
                """, stepId, runId, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, worker_id, input, status
                ) VALUES (?, ?, 1, 1, 'worker-a', CAST(? AS jsonb), 'running')
                """, taskId, stepId, "{}");
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

    private CleanRunStopLocalOpsRunner() {
    }
}
