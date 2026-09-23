package com.zthcpa.command.runtime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.CleanEventRepository;
import com.zthcpa.command.persistence.CleanTaskRepository;
import com.zthcpa.command.persistence.JdbcCleanEventRepository;
import com.zthcpa.command.persistence.JdbcCleanTaskRepository;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;
import java.util.Map;

public final class JdbcTaskDispatcherLocalOpsRunner {
    private static final String RUN_ID = "clean-dispatcher-selftest-run";
    private static final String STEP_ID = "clean-dispatcher-selftest-step";
    private static final String TASK_ID = "clean-dispatcher-selftest-task";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var mapper = new ObjectMapper();
        CleanTaskRepository taskRepository = new JdbcCleanTaskRepository(jdbc, mapper);
        CleanEventRepository eventRepository = new JdbcCleanEventRepository(jdbc, mapper);
        var completion = new CleanRunCompletionRepository(jdbc, mapper, dataSource);
        var port = new JdbcTaskExecutionPort(taskRepository, eventRepository, completion);
        var dispatcher = new TaskDispatcher(port, new SucceedingWorker());
        try {
            createFixture(jdbc);
            require(dispatcher.dispatchNext("worker-a"), "task must be dispatched");
            require(!dispatcher.dispatchNext("worker-a"), "queue must be empty");
            Map<String, Object> result = jdbc.getJdbcTemplate().queryForMap("""
                    SELECT
                      (SELECT status FROM command_runtime.runs WHERE id = ?) AS run_status,
                      (SELECT status FROM command_runtime.run_steps WHERE id = ?) AS step_status,
                      (SELECT status FROM command_runtime.task_executions WHERE id = ?) AS task_status,
                      (SELECT count(*) FROM command_runtime.task_events WHERE task_id = ?) AS task_events,
                      (SELECT count(*) FROM command_runtime.run_events WHERE run_id = ?) AS run_events
                    """, RUN_ID, STEP_ID, TASK_ID, TASK_ID, RUN_ID);
            System.out.println(result);
            require("succeeded".equals(result.get("run_status")), "run must succeed");
            require("succeeded".equals(result.get("step_status")), "step must succeed");
            require("succeeded".equals(result.get("task_status")), "task must succeed");
            require(((Number) result.get("task_events")).intValue() == 2, "worker and terminal events expected");
            require(((Number) result.get("run_events")).intValue() == 1, "terminal run event expected");
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
        }
    }

    private static final class SucceedingWorker implements WorkerRuntime {
        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            return new WorkerJob("job-1", "queued", null, null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            return new WorkerJob(jobId, "succeeded", Map.of("translated", "你好"), null);
        }

        @Override
        public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
            return List.of(new WorkerEvent(1, "progress", Map.of("percent", 100)));
        }

        @Override
        public void cancelJob(String jobId) {
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
                ) VALUES (?, ?, 0, 'text.llm.translate', 'tool', 'text.llm.translate', 1,
                          CAST(? AS jsonb), 'queued')
                """, STEP_ID, RUN_ID, "{}");
        jdbc.getJdbcTemplate().update("""
                INSERT INTO command_runtime.task_executions (
                    id, step_id, attempt, max_attempts, input, status
                ) VALUES (?, ?, 1, 1, CAST(? AS jsonb), 'queued')
                """, TASK_ID, STEP_ID, "{\"text\":\"hello\"}");
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

    private JdbcTaskDispatcherLocalOpsRunner() {
    }
}
