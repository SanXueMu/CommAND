package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.sql.DataSource;
import java.util.Map;

public final class CleanStepCoordinatorRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transaction;

    public CleanStepCoordinatorRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    }

    public boolean completeAndAdvance(
            String taskId,
            String workerId,
            TaskStatus terminalStatus,
            Map<String, Object> output,
            Map<String, Object> error,
            CleanNextStepPlan nextStep
    ) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (terminalStatus != TaskStatus.SUCCEEDED) {
            throw new IllegalArgumentException("Only successful tasks can advance to a next step");
        }

        Boolean completed = transaction.execute(status -> {
            String stepId = jdbc.query(COMPLETE_TASK, parameters(taskId, workerId, output, error),
                    resultSet -> resultSet.next() ? resultSet.getString("step_id") : null);
            if (stepId == null) {
                return false;
            }
            String runId = jdbc.queryForObject(FIND_RUN_ID, Map.of("stepId", stepId), String.class);
            jdbc.update(COMPLETE_STEP, Map.of("stepId", stepId));
            insertTaskEvent(taskId, "task.succeeded", output == null ? Map.of() : output);

            if (nextStep == null) {
                jdbc.update(COMPLETE_RUN, Map.of("runId", runId));
                insertRunEvent(runId, stepId, "run.succeeded", Map.of());
            } else {
                insertNextStep(runId, nextStep);
                insertRunEvent(runId, stepId, "step.advanced", Map.of("next_step_id", nextStep.stepId()));
            }
            return true;
        });
        return Boolean.TRUE.equals(completed);
    }

    private void insertNextStep(String runId, CleanNextStepPlan nextStep) {
        jdbc.update(INSERT_STEP, new MapSqlParameterSource()
                .addValue("stepId", nextStep.stepId())
                .addValue("runId", runId)
                .addValue("stepIndex", nextStep.stepIndex())
                .addValue("stepKey", nextStep.stepKey())
                .addValue("definitionId", nextStep.tool().id())
                .addValue("definitionVersion", nextStep.tool().version())
                .addValue("input", PostgresJson.write(mapper, nextStep.input())));
        jdbc.update(INSERT_TASK, new MapSqlParameterSource()
                .addValue("taskId", nextStep.taskId())
                .addValue("stepId", nextStep.stepId())
                .addValue("maxAttempts", nextStep.maxAttempts())
                .addValue("input", PostgresJson.write(mapper, nextStep.input())));
        insertTaskEvent(nextStep.taskId(), "task.queued", Map.of("step_index", nextStep.stepIndex()));
    }

    private void insertTaskEvent(String taskId, String kind, Map<String, Object> detail) {
        jdbc.update(INSERT_TASK_EVENT, new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("kind", kind)
                .addValue("detail", PostgresJson.write(mapper, detail)));
    }

    private void insertRunEvent(String runId, String stepId, String kind, Map<String, Object> detail) {
        jdbc.update(INSERT_RUN_EVENT, new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("stepId", stepId)
                .addValue("kind", kind)
                .addValue("detail", PostgresJson.write(mapper, detail)));
    }

    private MapSqlParameterSource parameters(
            String taskId, String workerId, Map<String, Object> output, Map<String, Object> error
    ) {
        return new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("workerId", workerId)
                .addValue("output", PostgresJson.write(mapper, output == null ? Map.of() : output))
                .addValue("error", PostgresJson.write(mapper, error));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static final String COMPLETE_TASK = """
            UPDATE command_runtime.task_executions
            SET status = 'succeeded', output = CAST(:output AS jsonb),
                error = CAST(:error AS jsonb), finished_at = now()
            WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
            RETURNING step_id
            """;

    private static final String FIND_RUN_ID = """
            SELECT run_id FROM command_runtime.run_steps WHERE id = :stepId
            """;

    private static final String COMPLETE_STEP = """
            UPDATE command_runtime.run_steps
            SET status = 'succeeded', finished_at = now()
            WHERE id = :stepId AND status = 'running'
            """;

    private static final String COMPLETE_RUN = """
            UPDATE command_runtime.runs
            SET status = 'succeeded', finished_at = now()
            WHERE id = :runId AND status = 'running'
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

    private static final String INSERT_TASK_EVENT = """
            INSERT INTO command_runtime.task_events (task_id, kind, detail)
            VALUES (:taskId, :kind, CAST(:detail AS jsonb))
            """;

    private static final String INSERT_RUN_EVENT = """
            INSERT INTO command_runtime.run_events (run_id, step_id, kind, actor, detail)
            VALUES (:runId, :stepId, :kind, 'system', CAST(:detail AS jsonb))
            """;
}
