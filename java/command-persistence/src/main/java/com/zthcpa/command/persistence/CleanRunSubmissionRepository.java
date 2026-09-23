package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.run.RunSubmissionPlan;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.sql.DataSource;

public final class CleanRunSubmissionRepository {
    private static final String INSERT_RUN = """
            INSERT INTO command_runtime.runs (
                id, workflow_id, workflow_version, input, status
            ) VALUES (
                :runId, :workflowId, :workflowVersion, CAST(:input AS jsonb), 'running'
            )
            """;

    private static final String INSERT_SNAPSHOT = """
            INSERT INTO command_runtime.run_definition_snapshots (
                run_id, definition_kind, definition_id, definition_version,
                schema_version, checksum, document
            ) VALUES (
                :runId, :kind, :definitionId, :definitionVersion,
                :schemaVersion, :checksum, CAST(:document AS jsonb)
            )
            """;

    private static final String INSERT_STEP = """
            INSERT INTO command_runtime.run_steps (
                id, run_id, step_index, step_key, definition_kind,
                definition_id, definition_version, input, status
            ) VALUES (
                :stepId, :runId, :stepIndex, :stepKey, 'tool',
                :definitionId, :definitionVersion, CAST(:input AS jsonb), 'queued'
            )
            """;

    private static final String INSERT_TASK = """
            INSERT INTO command_runtime.task_executions (
                id, step_id, attempt, max_attempts, input, status
            ) VALUES (
                :taskId, :stepId, 1, :maxAttempts, CAST(:input AS jsonb), 'queued'
            )
            """;

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transaction;

    public CleanRunSubmissionRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    }

    public void submit(RunSubmissionPlan plan) {
        transaction.executeWithoutResult(status -> {
            jdbc.update(INSERT_RUN, runParameters(plan));
            for (DefinitionDocument definition : plan.definitions()) {
                jdbc.update(INSERT_SNAPSHOT, snapshotParameters(plan.runId(), definition));
            }
            String stepId = plan.runId() + ":step:" + plan.firstTask().stepIndex();
            jdbc.update(INSERT_STEP, stepParameters(plan, stepId));
            jdbc.update(INSERT_TASK, taskParameters(plan, stepId));
        });
    }

    private MapSqlParameterSource runParameters(RunSubmissionPlan plan) {
        return new MapSqlParameterSource()
                .addValue("runId", plan.runId())
                .addValue("workflowId", plan.workflow().id())
                .addValue("workflowVersion", plan.workflow().version())
                .addValue("input", PostgresJson.write(mapper, plan.input()));
    }

    private MapSqlParameterSource snapshotParameters(String runId, DefinitionDocument definition) {
        return new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("kind", definition.key().kind().value())
                .addValue("definitionId", definition.key().id())
                .addValue("definitionVersion", definition.key().version())
                .addValue("schemaVersion", definition.schemaVersion())
                .addValue("checksum", definition.checksum())
                .addValue("document", PostgresJson.write(mapper, definition.content()));
    }

    private MapSqlParameterSource stepParameters(RunSubmissionPlan plan, String stepId) {
        return new MapSqlParameterSource()
                .addValue("stepId", stepId)
                .addValue("runId", plan.runId())
                .addValue("stepIndex", plan.firstTask().stepIndex())
                .addValue("stepKey", plan.firstTask().tool().id())
                .addValue("definitionId", plan.firstTask().tool().id())
                .addValue("definitionVersion", plan.firstTask().tool().version())
                .addValue("input", PostgresJson.write(mapper, plan.firstTask().input()));
    }

    private MapSqlParameterSource taskParameters(RunSubmissionPlan plan, String stepId) {
        return new MapSqlParameterSource()
                .addValue("taskId", plan.firstTask().handle())
                .addValue("stepId", stepId)
                .addValue("maxAttempts", plan.firstTask().maxAttempts())
                .addValue("input", PostgresJson.write(mapper, plan.firstTask().input()));
    }
}
