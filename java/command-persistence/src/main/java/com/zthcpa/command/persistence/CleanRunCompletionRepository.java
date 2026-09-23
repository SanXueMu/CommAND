package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.RunStatus;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.sql.DataSource;
import java.util.Map;

public final class CleanRunCompletionRepository {
    private static final String COMPLETE_TASK = """
            UPDATE command_runtime.task_executions
            SET status = :taskStatus, output = CAST(:output AS jsonb),
                error = CAST(:error AS jsonb), finished_at = now()
            WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
            RETURNING step_id
            """;

    private static final String FIND_RUN_ID = """
            SELECT run_id
            FROM command_runtime.run_steps
            WHERE id = :stepId
            """;

    private static final String COMPLETE_STEP = """
            UPDATE command_runtime.run_steps
            SET status = :stepStatus, finished_at = now()
            WHERE id = :stepId AND status = 'running'
            """;

    private static final String COMPLETE_RUN = """
            UPDATE command_runtime.runs
            SET status = :runStatus, error = CAST(:error AS jsonb), finished_at = now()
            WHERE id = :runId AND status = 'running'
            """;

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transaction;

    public CleanRunCompletionRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    }

    public boolean completeTask(
            String taskId,
            String workerId,
            TaskStatus taskStatus,
            Map<String, Object> output,
            Map<String, Object> error
    ) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (taskStatus == null || !taskStatus.terminal()) {
            throw new IllegalArgumentException("Task completion status must be terminal");
        }

        Boolean completed = transaction.execute(status -> {
            String stepId = jdbc.query(COMPLETE_TASK, new MapSqlParameterSource()
                            .addValue("taskId", taskId)
                            .addValue("workerId", workerId)
                            .addValue("taskStatus", taskStatus.name().toLowerCase())
                            .addValue("output", PostgresJson.write(mapper, output))
                            .addValue("error", PostgresJson.write(mapper, error)),
                    resultSet -> resultSet.next() ? resultSet.getString("step_id") : null);
            if (stepId == null) {
                return false;
            }

            String runId = jdbc.queryForObject(FIND_RUN_ID, Map.of("stepId", stepId), String.class);
            RunStatus runStatus = toRunStatus(taskStatus);
            String stepStatus = toStepStatus(taskStatus);
            jdbc.update(COMPLETE_STEP, Map.of("stepId", stepId, "stepStatus", stepStatus));
            jdbc.update(COMPLETE_RUN, new MapSqlParameterSource()
                    .addValue("runId", runId)
                    .addValue("runStatus", runStatus.name().toLowerCase())
                    .addValue("error", PostgresJson.write(mapper, error)));

            insertTaskEvent(taskId, taskStatus, error);
            insertRunEvent(runId, stepId, runStatus, error);
            return true;
        });
        return Boolean.TRUE.equals(completed);
    }

    public boolean failTask(
            String taskId,
            String workerId,
            TaskStatus failureStatus,
            Map<String, Object> error
    ) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (failureStatus != TaskStatus.FAILED && failureStatus != TaskStatus.FAILED_REVIEW) {
            throw new IllegalArgumentException("Failure status must be FAILED or FAILED_REVIEW");
        }

        Boolean failed = transaction.execute(status -> {
            String stepId = jdbc.query(COMPLETE_TASK, new MapSqlParameterSource()
                            .addValue("taskId", taskId)
                            .addValue("workerId", workerId)
                            .addValue("taskStatus", failureStatus.name().toLowerCase())
                            .addValue("output", PostgresJson.write(mapper, Map.of()))
                            .addValue("error", PostgresJson.write(mapper, error == null ? Map.of() : error)),
                    resultSet -> resultSet.next() ? resultSet.getString("step_id") : null);
            if (stepId == null) {
                return false;
            }
            String runId = jdbc.queryForObject(FIND_RUN_ID, Map.of("stepId", stepId), String.class);
            jdbc.update(COMPLETE_STEP, new MapSqlParameterSource()
                    .addValue("stepId", stepId)
                    .addValue("stepStatus", failureStatus == TaskStatus.FAILED_REVIEW ? "failed" : "failed"));
            jdbc.update(COMPLETE_RUN, new MapSqlParameterSource()
                    .addValue("runId", runId)
                    .addValue("runStatus", failureStatus == TaskStatus.FAILED_REVIEW ? "failed_review" : "failed")
                    .addValue("error", PostgresJson.write(mapper, error == null ? Map.of() : error)));
            insertTaskEvent(taskId, failureStatus, error);
            insertRunEvent(runId, stepId, toRunStatus(failureStatus), error);
            return true;
        });
        return Boolean.TRUE.equals(failed);
    }

    private void insertTaskEvent(String taskId, TaskStatus status, Map<String, Object> error) {
        jdbc.update("""
                INSERT INTO command_runtime.task_events (task_id, kind, detail)
                VALUES (:taskId, :kind, CAST(:detail AS jsonb))
                """, new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("kind", "task." + status.name().toLowerCase())
                .addValue("detail", PostgresJson.write(mapper, error == null ? Map.of() : error)));
    }

    private void insertRunEvent(String runId, String stepId, RunStatus status, Map<String, Object> error) {
        jdbc.update("""
                INSERT INTO command_runtime.run_events (run_id, step_id, kind, actor, detail)
                VALUES (:runId, :stepId, :kind, 'system', CAST(:detail AS jsonb))
                """, new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("stepId", stepId)
                .addValue("kind", "run." + status.name().toLowerCase())
                .addValue("detail", PostgresJson.write(mapper, error == null ? Map.of() : error)));
    }

    private static RunStatus toRunStatus(TaskStatus status) {
        return switch (status) {
            case SUCCEEDED -> RunStatus.SUCCEEDED;
            case CANCELLED -> RunStatus.CANCELLED;
            case INTERRUPTED -> RunStatus.INTERRUPTED;
            case FAILED_REVIEW -> RunStatus.FAILED_REVIEW;
            case FAILED -> RunStatus.FAILED;
            default -> throw new IllegalArgumentException("Unsupported terminal task status: " + status);
        };
    }

    private static String toStepStatus(TaskStatus status) {
        return switch (status) {
            case SUCCEEDED -> "succeeded";
            case CANCELLED -> "cancelled";
            case INTERRUPTED -> "failed";
            case FAILED_REVIEW, FAILED -> "failed";
            default -> throw new IllegalArgumentException("Unsupported terminal task status: " + status);
        };
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
