package com.zthcpa.command;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.http.MediaType.APPLICATION_JSON;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class RunApiIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper mapper;

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
    void submitsAndReadsCleanRunWithoutLeakingInternalTaskFields() throws Exception {
        String body = mapper.writeValueAsString(Map.of(
                "workflowId", "ocr.extract-document",
                "workflowVersion", 1,
                "input", Map.of("file", "sample.pdf")
        ));

        String response = mockMvc.perform(post("/api/runs")
                        .contentType(APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").isString())
                .andExpect(jsonPath("$.status", is("running")))
                .andExpect(jsonPath("$.firstTaskHandle").isString())
                .andReturn()
                .getResponse()
                .getContentAsString();
        runId = mapper.readTree(response).get("runId").asText();

        mockMvc.perform(get("/api/runs/{runId}", runId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId", is(runId)))
                .andExpect(jsonPath("$.steps", hasSize(1)))
                .andExpect(jsonPath("$.steps[0].task.attempt", is(1)))
                .andExpect(jsonPath("$.steps[0].task.id").doesNotExist())
                .andExpect(jsonPath("$.steps[0].task.input.file", is("sample.pdf")));
    }

    @Test
    void returnsBadRequestForMissingWorkflow() throws Exception {
        mockMvc.perform(post("/api/runs")
                        .contentType(APPLICATION_JSON)
                        .content("{\"input\":{}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code", is("RUN_SUBMISSION_INVALID")));
    }

    @Test
    void exposesEnabledSchedulerStatusWithoutWorkerDetails() throws Exception {
        mockMvc.perform(get("/api/system/scheduler"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true))
                .andExpect(jsonPath("$.active").value(true))
                .andExpect(jsonPath("$.workerBaseUrl").doesNotExist());
    }

    @Test
    void readsRunEventsWithAfterIdCursor() throws Exception {
        String body = mapper.writeValueAsString(Map.of(
                "workflowId", "ocr.extract-document",
                "workflowVersion", 1,
                "input", Map.of("file", "events.pdf")
        ));
        String response = mockMvc.perform(post("/api/runs")
                        .contentType(APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn()
                .getResponse()
                .getContentAsString();
        runId = mapper.readTree(response).get("runId").asText();

        Number firstId = jdbc.queryForObject(
                "INSERT INTO command_runtime.run_events (run_id, kind, actor, detail) "
                        + "VALUES (?, 'run.started', 'test', '{}'::jsonb) RETURNING id",
                Number.class,
                runId
        );
        jdbc.update(
                "INSERT INTO command_runtime.run_events (run_id, kind, actor, detail) "
                        + "VALUES (?, 'run.progress', 'test', '{\"percent\":50}'::jsonb)",
                runId
        );

        mockMvc.perform(get("/api/runs/{runId}/events", runId)
                        .param("afterId", String.valueOf(firstId.longValue()))
                        .param("limit", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].kind", is("run.progress")))
                .andExpect(jsonPath("$[0].detail.percent", is(50)));
    }

    @Test
    void returnsNotFoundForEventsOfUnknownRun() throws Exception {
        mockMvc.perform(get("/api/runs/unknown-run/events"))
                .andExpect(status().isNotFound());
    }

    @Test
    void streamsEventsAndClosesAfterTerminalRun() throws Exception {
        String body = mapper.writeValueAsString(Map.of(
                "workflowId", "ocr.extract-document",
                "workflowVersion", 1,
                "input", Map.of("file", "stream.pdf")
        ));
        String response = mockMvc.perform(post("/api/runs")
                        .contentType(APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn()
                .getResponse()
                .getContentAsString();
        runId = mapper.readTree(response).get("runId").asText();
        jdbc.update("UPDATE command_runtime.runs SET status = 'succeeded', finished_at = CURRENT_TIMESTAMP WHERE id = ?", runId);
        jdbc.update(
                "INSERT INTO command_runtime.run_events (run_id, kind, actor, detail) "
                        + "VALUES (?, 'run.succeeded', 'test', '{}'::jsonb)",
                runId
        );

        var async = mockMvc.perform(get("/api/runs/{runId}/events/stream", runId))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(async))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/event-stream"))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("run.succeeded")));
    }

    @AfterEach
    void cleanup() {
        if (runId != null) {
            jdbc.update("DELETE FROM command_runtime.runs WHERE id = ?", runId);
        }
    }
}
