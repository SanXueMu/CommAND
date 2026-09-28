package com.zthcpa.command;

import com.zthcpa.command.persistence.run.CleanStepCoordinatorRepository;
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

@SpringBootTest
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class CleanPipelineInputMappingIntegrationTest {
    @Autowired
    private CleanStepCoordinatorRepository coordinator;

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
    void resolvesPreviousStepOutputIntoNextQueuedTask() {
        runId = "mapping-" + UUID.randomUUID();
        String firstStepId = PipelineExecutionIdentifiers.stepId(runId, 0);
        String firstTaskId = PipelineExecutionIdentifiers.taskId(runId, 0);
        String pipeline = """
                {"schema_version":1,"kind":"capability_pipeline","id":"test.mapping","version":1,
                 "status":"active","title":"Mapping",
                 "steps":[
                   {"id":"inspect","definition_ref":{"kind":"tool","id":"file.inspect","version":1}},
                   {"id":"extract","definition_ref":{"kind":"tool","id":"ocr.page.extract","version":1},
                    "input":{"file":"$run.file","page":"$step.inspect.pages.0"}}
                 ]}
                """;
        jdbc.update("INSERT INTO command_runtime.runs (id, workflow_id, workflow_version, input, status) "
                        + "VALUES (?, 'test.workflow', 1, ?::jsonb, 'running')",
                runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.run_definition_snapshots "
                        + "(run_id, definition_kind, definition_id, definition_version, schema_version, checksum, document) "
                        + "VALUES (?, 'capability_pipeline', 'test.mapping', 1, 1, ?, ?::jsonb)",
                runId, "0".repeat(64), pipeline);
        jdbc.update("INSERT INTO command_runtime.run_steps "
                        + "(id, run_id, step_index, step_key, definition_kind, definition_id, definition_version, input, status) "
                        + "VALUES (?, ?, 0, 'inspect', 'tool', 'file.inspect', 1, ?::jsonb, 'running')",
                firstStepId, runId, "{\"file\":\"sample.pdf\"}");
        jdbc.update("INSERT INTO command_runtime.task_executions "
                        + "(id, step_id, attempt, max_attempts, worker_id, input, status) "
                        + "VALUES (?, ?, 1, 1, 'mapping-worker', ?::jsonb, 'running')",
                firstTaskId, firstStepId, "{\"file\":\"sample.pdf\"}");

        coordinator.completeAndAdvance(firstTaskId, "mapping-worker", Map.of("pages", java.util.List.of(7, 9)));

        Map<String, Object> nextInput = jdbc.queryForMap(
                "SELECT input FROM command_runtime.task_executions WHERE step_id = ?",
                PipelineExecutionIdentifiers.stepId(runId, 1));
        assertEquals("sample.pdf", jsonText(nextInput.get("input"), "file"));
        assertEquals(7, jsonNumber(jsonText(nextInput.get("input"), "page")));
    }

    private String jsonText(Object json, String field) {
        return jdbc.queryForObject("SELECT (?::jsonb ->> ?)", String.class, json.toString(), field);
    }

    private int jsonNumber(String value) {
        return Integer.parseInt(value);
    }

    @AfterEach
    void cleanup() {
        if (runId != null) {
            jdbc.update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }
}
