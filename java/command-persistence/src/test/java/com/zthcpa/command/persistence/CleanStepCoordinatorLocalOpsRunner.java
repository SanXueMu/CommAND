package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.run.TaskStatus;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanStepCoordinatorLocalOpsRunner {
    private static final String RUN_ID = "clean-step-selftest-run";
    private static final String STEP_ONE = "clean-step-selftest-step-1";
    private static final String TASK_ONE = "clean-step-selftest-task-1";
    private static final String STEP_TWO = "clean-step-selftest-step-2";
    private static final String TASK_TWO = "clean-step-selftest-task-2";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var mapper = new ObjectMapper();
        var coordinator = new CleanStepCoordinatorRepository(jdbc, mapper, dataSource);
        var taskRepository = new JdbcCleanTaskRepository(jdbc, mapper);
        var completion = new CleanRunCompletionRepository(jdbc, mapper, dataSource);
        try {
            createFixture(jdbc);
            require(coordinator.completeAndAdvance(
                    TASK_ONE, "worker-a", TaskStatus.SUCCEEDED,
                    Map.of("stage", 1), null,
                    new CleanNextStepPlan(
                            STEP_TWO, 1, "second-tool", new DefinitionKey(
                                    com.zthcpa.command.contract.DefinitionKind.TOOL, "second-tool", 1
                            ), Map.of("from", "step-1"), TASK_TWO, 1
                    )
            ), "first step must advance");
            String running = jdbc.getJdbcTemplate().queryForObject(
                    "SELECT status FROM command_runtime.runs WHERE id = ?", String.class, RUN_ID);
            require("running".equals(running), "run must remain running after advance");

            require(taskRepository.claimNext("worker-b").isPresent(), "second step must be claimed");
            require(completion.completeTask(TASK_TWO, "worker-b", TaskStatus.SUCCEEDED,
                    Map.of("stage", 2), null), "second step must complete");
            String succeeded = jdbc.getJdbcTemplate().queryForObject(
                    "SELECT status FROM command_runtime.runs WHERE id = ?", String.class, RUN_ID);
            long steps = jdbc.getJdbcTemplate().queryForObject(
                    "SELECT count(*) FROM command_runtime.run_steps WHERE run_id = ?", Long.class, RUN_ID);
            long tasks = jdbc.getJdbcTemplate().queryForObject("""
                    SELECT count(*) FROM command_runtime.task_executions t
                    JOIN command_runtime.run_steps s ON s.id = t.step_id
                    WHERE s.run_id = ?
                    """, Long.class, RUN_ID);
            System.out.println("after advance: run=" + running + ", steps=" + steps + ", tasks=" + tasks
                    + "; final run=" + succeeded);
            require("succeeded".equals(succeeded), "run must succeed after final step");
            require(steps == 2 && tasks == 2, "two steps and tasks expected");
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
                ) VALUES (?, ?, 0, 'first-tool', 'tool', 'first-tool', 1,
                          CAST(? AS jsonb), 'running')
                """, STEP_ONE, RUN_ID, "{}"
        );
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, worker_id, input, status
                ) VALUES (?, ?, 1, 1, 'worker-a', CAST(? AS jsonb), 'running')
                """, TASK_ONE, STEP_ONE, "{}"
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

    private CleanStepCoordinatorLocalOpsRunner() {
    }
}
