package com.zthcpa.command;

import com.zthcpa.command.persistence.run.CleanRecoveryRepository;
import com.zthcpa.command.run.PipelineExecutionIdentifiers;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.util.Map;
import java.util.UUID;
import java.time.Instant;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class CleanPipelineRecoveryInputIntegrationTest {
    @Autowired
    private CleanRecoveryRepository recovery;

    @Autowired
    private JdbcTemplate jdbc;

    private String runId;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void recoveryKeepsResolvedInputAndIgnoresInterruptedOutput() {
        runId = "recovery-mapping-" + UUID.randomUUID();
        String firstStepId = PipelineExecutionIdentifiers.stepId(runId, 0);
        String firstTaskId = PipelineExecutionIdentifiers.taskId(runId, 0);
        String secondStepId = PipelineExecutionIdentifiers.stepId(runId, 1);
        String secondTaskId = PipelineExecutionIdentifiers.taskId(runId, 1);
        String pipeline = """
                {"schema_version":1,"kind":"capability_pipeline","id":"test.recovery-mapping","version":1,
                 "status":"active","title":"Recovery mapping",
                 "steps":[
                   {"id":"inspect","definition_ref":{"kind":"tool","id":"file.inspect","version":1}},
                   {"id":"extract","definition_ref":{"kind":"tool","id":"ocr.page.extract","version":1},
                    "input":{"file":"$run.file","page":"$step.inspect.pages.0"}}
                 ]}
                """;
        jdbc.update("INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, ?::jsonb, 'interrupted')",
                runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.run_definition_snapshots "
                        + "(run_id, definition_kind, definition_id, definition_version, schema_version, checksum, document) "
                        + "VALUES (?, 'capability_pipeline', 'test.recovery-mapping', 1, 1, ?, ?::jsonb)",
                runId, "0".repeat(64), pipeline);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 0, 'inspect', 'tool', 'file.inspect', 1, ?::jsonb, 'succeeded')",
                firstStepId, runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, input, output, status) "
                        + "VALUES (?, ?, 1, 1, ?::jsonb, ?::jsonb, 'succeeded')",
                firstTaskId, firstStepId, "{\"file\":\"sample.pdf\"}", "{\"pages\":[7,9]}");
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 1, 'extract', 'tool', 'ocr.page.extract', 1, ?::jsonb, 'interrupted')",
                secondStepId, runId, "{\"file\":\"sample.pdf\",\"page\":7}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, input, output, status) "
                        + "VALUES (?, ?, 1, 2, ?::jsonb, ?::jsonb, 'interrupted')",
                secondTaskId, secondStepId, "{\"file\":\"sample.pdf\",\"page\":7}", "{\"partial\":true}");

        assertEquals(true, recovery.recoverInterruptedRun(runId));

        Map<String, Object> retry = jdbc.queryForMap(
                "SELECT input, output, status, attempt FROM command_runtime.task_executions WHERE id = ?",
                PipelineExecutionIdentifiers.recoveryTaskId(runId, 1, 2));
        assertEquals("sample.pdf", jsonText(retry.get("input"), "file"));
        assertEquals("7", jsonText(retry.get("input"), "page"));
        assertEquals("queued", retry.get("status"));
        assertEquals(2, retry.get("attempt"));
        assertEquals(null, retry.get("output"));
        assertFalse(recovery.recoverInterruptedRun(runId));
    }

    @Test
    void staleRecoveryAlsoCreatesTheNextAttemptWithTheSameResolvedInput() {
        runId = "stale-mapping-" + UUID.randomUUID();
        String stepId = PipelineExecutionIdentifiers.stepId(runId, 1);
        String taskId = PipelineExecutionIdentifiers.taskId(runId, 1);
        jdbc.update("INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, '{}'::jsonb, 'running')", runId);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 1, 'extract', 'tool', 'ocr.page.extract', 1, ?::jsonb, 'running')",
                stepId, runId, "{\"file\":\"sample.pdf\",\"page\":7}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, worker_id, input, heartbeat_at, status) "
                        + "VALUES (?, ?, 1, 2, 'stale-worker', ?::jsonb, ?, 'running')",
                taskId, stepId, "{\"file\":\"sample.pdf\",\"page\":7}",
                java.sql.Timestamp.from(Instant.now().minusSeconds(120)));

        assertEquals(1, recovery.recoverStaleTasks(Instant.now().minusSeconds(60), 10));

        Map<String, Object> retry = jdbc.queryForMap(
                "SELECT input, output, status, attempt FROM command_runtime.task_executions WHERE id = ?",
                PipelineExecutionIdentifiers.recoveryTaskId(runId, 1, 2));
        assertEquals("sample.pdf", jsonText(retry.get("input"), "file"));
        assertEquals("7", jsonText(retry.get("input"), "page"));
        assertEquals("queued", retry.get("status"));
        assertEquals(2, retry.get("attempt"));
        assertEquals(null, retry.get("output"));
    }

    @Test
    void recoveryDoesNotCreateRetryAfterMaximumAttempts() {
        runId = "recovery-exhausted-" + UUID.randomUUID();
        String stepId = PipelineExecutionIdentifiers.stepId(runId, 1);
        String taskId = PipelineExecutionIdentifiers.taskId(runId, 1);
        jdbc.update("INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, '{}'::jsonb, 'interrupted')", runId);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 1, 'extract', 'tool', 'ocr.page.extract', 1, ?::jsonb, 'interrupted')",
                stepId, runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, input, status) "
                        + "VALUES (?, ?, 2, 2, ?::jsonb, 'interrupted')",
                taskId, stepId, "{\"file\":\"sample.pdf\"}");

        assertFalse(recovery.recoverInterruptedRun(runId));
        assertEquals(1, jdbc.queryForObject(
                "SELECT count(*) FROM command_runtime.task_executions WHERE step_id = ?", Integer.class, stepId));
        assertEquals("interrupted", jdbc.queryForObject(
                "SELECT status FROM command_runtime.task_executions WHERE id = ?", String.class, taskId));
    }

    @Test
    void concurrentStaleRecoveryCreatesOnlyOneRetry() throws Exception {
        runId = "stale-concurrent-" + UUID.randomUUID();
        String stepId = PipelineExecutionIdentifiers.stepId(runId, 1);
        String taskId = PipelineExecutionIdentifiers.taskId(runId, 1);
        jdbc.update("INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, '{}'::jsonb, 'running')", runId);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 1, 'extract', 'tool', 'ocr.page.extract', 1, ?::jsonb, 'running')",
                stepId, runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, worker_id, input, heartbeat_at, status) "
                        + "VALUES (?, ?, 1, 2, 'stale-worker', ?::jsonb, ?, 'running')",
                taskId, stepId, "{\"file\":\"sample.pdf\"}",
                java.sql.Timestamp.from(Instant.now().minusSeconds(120)));

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = executor.submit(() -> recovery.recoverStaleTasks(Instant.now().minusSeconds(60), 10));
            Future<Integer> second = executor.submit(() -> recovery.recoverStaleTasks(Instant.now().minusSeconds(60), 10));
            assertTrue(first.get() + second.get() == 1);
        } finally {
            executor.shutdownNow();
        }
        assertEquals(2, jdbc.queryForObject(
                "SELECT count(*) FROM command_runtime.task_executions WHERE step_id = ?", Integer.class, stepId));
        assertEquals(1, jdbc.queryForObject(
                "SELECT count(*) FROM command_runtime.task_executions WHERE step_id = ? AND status = 'queued'",
                Integer.class, stepId));
    }

    private String jsonText(Object json, String field) {
        return jdbc.queryForObject("SELECT (?::jsonb ->> ?)", String.class, json.toString(), field);
    }

    @AfterEach
    void cleanup() {
        if (runId != null) {
            jdbc.update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }
}
