package com.zthcpa.command;

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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "command.clean.scheduler.enabled=true",
        "command.clean.scheduler.worker-id=java-pipeline-test",
        "command.clean.scheduler.poll-interval=20ms",
        "command.clean.scheduler.job-poll-interval=10ms",
        "command.clean.scheduler.job-timeout=10s",
        "command.clean.scheduler.heartbeat-interval=1s"
})
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class JavaToolPipelineSchedulerIntegrationTest {
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
    void schedulerExecutesJavaToolsAndPropagatesPipelineOutput() throws Exception {
        runId = "java-pipeline-" + UUID.randomUUID();
        String firstStepId = PipelineExecutionIdentifiers.stepId(runId, 0);
        String firstTaskId = PipelineExecutionIdentifiers.taskId(runId, 0);
        String secondStepId = PipelineExecutionIdentifiers.stepId(runId, 1);

        String pipeline = """
                {"schema_version":1,"kind":"capability_pipeline","id":"test.java-tools","version":1,
                 "status":"active","title":"Java tools",
                 "steps":[
                   {"id":"merge","definition_ref":{"kind":"tool","id":"records.merge.crosspage","version":1}},
                   {"id":"merge-again","definition_ref":{"kind":"tool","id":"records.merge.crosspage","version":1},
                    "input":{"records":"$step.merge.records","key_field":"key","modes":["join"]}}
                 ]}
                """;
        String input = """
                {"records":[{"key":"A","value":"first"},{"key":"","value":"second"}],
                 "key_field":"key","modes":["join"]}
                """;

        jdbc.update("INSERT INTO command_runtime.runs "
                        + "(id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, ?::jsonb, 'running')",
                runId, input);
        jdbc.update("INSERT INTO command_runtime.run_definition_snapshots "
                        + "(run_id, definition_kind, definition_id, definition_version, schema_version, checksum, document) "
                        + "VALUES (?, 'capability_pipeline', 'test.java-tools', 1, 1, ?, ?::jsonb)",
                runId, "0".repeat(64), pipeline);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 0, 'merge', 'tool', 'records.merge.crosspage', 1, ?::jsonb, 'queued')",
                firstStepId, runId, input);
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, input, status) "
                        + "VALUES (?, ?, 1, 1, ?::jsonb, 'queued')",
                firstTaskId, firstStepId, input);

        awaitRunSucceeded();

        assertEquals(2, jdbc.queryForObject(
                "SELECT count(*) FROM command_runtime.run_steps WHERE run_id = ? AND status = 'succeeded'",
                Integer.class, runId));
        assertEquals("succeeded", jdbc.queryForObject(
                "SELECT status FROM command_runtime.runs WHERE id = ?", String.class, runId));
        assertEquals("first；second", jdbc.queryForObject(
                "SELECT output -> 'records' -> 0 ->> 'value' "
                        + "FROM command_runtime.task_executions WHERE id = ?",
                String.class, firstTaskId));
        assertEquals("first；second", jdbc.queryForObject(
                "SELECT input -> 'records' -> 0 ->> 'value' "
                        + "FROM command_runtime.task_executions WHERE step_id = ?",
                String.class, secondStepId));
        assertTrue(jdbc.queryForObject(
                "SELECT count(*) FROM command_runtime.task_events e "
                        + "JOIN command_runtime.task_executions t ON t.id = e.task_id "
                        + "JOIN command_runtime.run_steps s ON s.id = t.step_id "
                        + "WHERE s.run_id = ? AND e.kind = 'worker.progress'",
                Integer.class, runId) >= 2);
    }

    private void awaitRunSucceeded() throws InterruptedException {
        long deadline = System.nanoTime() + 10_000_000_000L;
        while (System.nanoTime() < deadline) {
            String status = jdbc.queryForObject(
                    "SELECT status FROM command_runtime.runs WHERE id = ?", String.class, runId);
            if ("succeeded".equals(status)) return;
            Thread.sleep(50);
        }
        Map<String, Object> state = jdbc.queryForMap(
                "SELECT status, error FROM command_runtime.runs WHERE id = ?", runId);
        throw new AssertionError("Timed out waiting for Java Tool pipeline: " + state);
    }

    @AfterEach
    void cleanup() {
        if (runId != null) {
            jdbc.update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }
}
