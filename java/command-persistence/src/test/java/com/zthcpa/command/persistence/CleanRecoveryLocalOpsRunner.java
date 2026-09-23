package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanRecoveryLocalOpsRunner {
    public static void main(String[] args) {
        runCase("interrupted", "interrupted", true);
        runCase("cancelled", "cancelled", false);
    }

    private static void runCase(String suffix, String runStatus, boolean expectedRecovery) {
        String runId = "clean-recovery-selftest-" + suffix + "-run";
        String stepId = "clean-recovery-selftest-" + suffix + "-step";
        String taskId = "clean-recovery-selftest-" + suffix + "-task";

        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new CleanRecoveryRepository(jdbc, new ObjectMapper(), dataSource);
        try {
            createFixture(jdbc, runId, stepId, taskId, runStatus);
            boolean recovered = repository.recoverInterruptedRun(runId);
            System.out.println(suffix + " recovered=" + recovered);
            require(recovered == expectedRecovery, "unexpected recovery result");
            if (expectedRecovery) {
                Map<String, Object> result = jdbc.getJdbcTemplate().queryForMap("""
                        SELECT
                          (SELECT status FROM command_runtime.runs WHERE id = ?) AS run_status,
                          (SELECT status FROM command_runtime.run_steps WHERE id = ?) AS step_status,
                          (SELECT max(attempt) FROM command_runtime.task_executions WHERE step_id = ?) AS max_attempt,
                          (SELECT count(*) FROM command_runtime.task_executions WHERE step_id = ?) AS task_count,
                          (SELECT count(*) FROM command_runtime.run_events WHERE run_id = ?) AS run_events
                        """, runId, stepId, stepId, stepId, runId);
                System.out.println(result);
                require("running".equals(result.get("run_status")), "run must be restored");
                require("running".equals(result.get("step_status")), "step must be restored");
                require(((Number) result.get("max_attempt")).intValue() == 2, "attempt must increment");
                require(((Number) result.get("task_count")).intValue() == 2, "retry task must be added");
                require(((Number) result.get("run_events")).intValue() == 1, "recovery event expected");
            }
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }

    private static void createFixture(
            NamedParameterJdbcTemplate jdbc, String runId, String stepId, String taskId, String runStatus
    ) {
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status)
                VALUES (?, 'test.workflow', 1, CAST(? AS jsonb), ?)
                """, runId, "{}", runStatus);
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.run_steps (
                    id, run_id, step_index, step_key, definition_kind,
                    definition_id, definition_version, input, status
                ) VALUES (?, ?, 0, 'recoverable-tool', 'tool', 'recoverable-tool', 1,
                          CAST(? AS jsonb), ?)
                """, stepId, runId, "{}", runStatus);
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, status
                ) VALUES (?, ?, 1, 2, CAST(? AS jsonb), ?)
                """, taskId, stepId, "{\"source\":\"interrupted\"}", runStatus);
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

    private CleanRecoveryLocalOpsRunner() {
    }
}
