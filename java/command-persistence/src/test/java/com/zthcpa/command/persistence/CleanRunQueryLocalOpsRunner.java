package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;

public final class CleanRunQueryLocalOpsRunner {
    private static final String RUN_ID = "clean-query-selftest-run";
    private static final String STEP_ID = "clean-query-selftest-step";
    private static final String TASK_ONE = "clean-query-selftest-task-1";
    private static final String TASK_TWO = "clean-query-selftest-task-2";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var mapper = new ObjectMapper();
        var events = new JdbcCleanEventRepository(jdbc, mapper);
        var query = new CleanRunQueryRepository(jdbc, mapper);
        try {
            createFixture(jdbc);
            events.appendRunEvent(RUN_ID, STEP_ID, "run.started", "system", Map.of("page", 1));
            long firstEvent = events.appendRunEvent(RUN_ID, STEP_ID, "run.progress", "worker-a", Map.of("page", 2));
            CleanRunSnapshot snapshot = query.get(RUN_ID);
            require(snapshot != null, "run detail must exist");
            require(snapshot.steps().size() == 1, "one step expected");
            require(snapshot.steps().get(0).latestTask() != null, "latest task expected");
            require(TASK_TWO.equals(snapshot.steps().get(0).latestTask().id()), "latest attempt expected");
            require(snapshot.steps().get(0).latestTask().attempt() == 2, "latest attempt number expected");
            require(query.list(0, 10).stream().anyMatch(run -> RUN_ID.equals(run.id())), "run list expected");
            require(query.listEvents(RUN_ID, firstEvent - 1, 10).size() == 1, "afterId event page expected");
            System.out.println("detail latest_task=" + snapshot.steps().get(0).latestTask().id()
                    + ", attempt=" + snapshot.steps().get(0).latestTask().attempt()
                    + ", afterId events=1");
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
        }
    }

    private static void createFixture(NamedParameterJdbcTemplate jdbc) {
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status)
                VALUES (?, 'test.workflow', 1, CAST(? AS jsonb), 'running')
                """, RUN_ID, "{\"query\":true}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.run_steps (
                    id, run_id, step_index, step_key, definition_kind,
                    definition_id, definition_version, input, status
                ) VALUES (?, ?, 0, 'query-tool', 'tool', 'query-tool', 1,
                          CAST(? AS jsonb), 'running')
                """, STEP_ID, RUN_ID, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, status
                ) VALUES (?, ?, 1, 2, CAST(? AS jsonb), 'interrupted')
                """, TASK_ONE, STEP_ID, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, output, status
                ) VALUES (?, ?, 2, 2, CAST(? AS jsonb), CAST(? AS jsonb), 'succeeded')
                """, TASK_TWO, STEP_ID, "{}", "{\"rows\":2}");
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

    private CleanRunQueryLocalOpsRunner() {
    }
}
