package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.sql.DataSource;
import java.util.Map;

public final class CleanRecoveryRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transaction;

    public CleanRecoveryRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    }

    public boolean recoverInterruptedRun(String runId) {
        require(runId, "Run id");
        Boolean recovered = transaction.execute(status -> {
            String stepId = jdbc.query(LOCK_STEP, Map.of("runId", runId),
                    resultSet -> resultSet.next() ? resultSet.getString("step_id") : null);
            if (stepId == null) {
                return false;
            }
            String taskId = jdbc.queryForObject(LOCK_TASK, Map.of("stepId", stepId), String.class);
            Map<String, Object> task = jdbc.queryForMap(TASK_DETAILS, Map.of("taskId", taskId));
            int attempt = ((Number) task.get("attempt")).intValue();
            int maxAttempts = ((Number) task.get("max_attempts")).intValue();
            if (attempt >= maxAttempts) {
                return false;
            }

            jdbc.update(RESTORE_RUN, Map.of("runId", runId));
            jdbc.update(RESTORE_STEP, Map.of("stepId", stepId));
            String newTaskId = taskId + ":retry:" + (attempt + 1);
            jdbc.update(INSERT_RETRY, new MapSqlParameterSource()
                    .addValue("taskId", newTaskId)
                    .addValue("stepId", stepId)
                    .addValue("attempt", attempt + 1)
                    .addValue("maxAttempts", maxAttempts)
                    .addValue("input", PostgresJson.write(mapper,
                            PostgresJson.read(mapper, task.get("input").toString()))));
            insertTaskEvent(newTaskId, "task.requeued", Map.of("attempt", attempt + 1));
            insertRunEvent(runId, stepId, "run.recovered", Map.of("task_id", newTaskId));
            return true;
        });
        return Boolean.TRUE.equals(recovered);
    }

    private void insertTaskEvent(String taskId, String kind, Map<String, Object> detail) {
        jdbc.update("""
                INSERT INTO command_runtime.task_events (task_id, kind, detail)
                VALUES (:taskId, :kind, CAST(:detail AS jsonb))
                """, new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("kind", kind)
                .addValue("detail", PostgresJson.write(mapper, detail)));
    }

    private void insertRunEvent(String runId, String stepId, String kind, Map<String, Object> detail) {
        jdbc.update("""
                INSERT INTO command_runtime.run_events (run_id, step_id, kind, actor, detail)
                VALUES (:runId, :stepId, :kind, 'system', CAST(:detail AS jsonb))
                """, new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("stepId", stepId)
                .addValue("kind", kind)
                .addValue("detail", PostgresJson.write(mapper, detail)));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static final String LOCK_STEP = """
            SELECT s.id AS step_id
            FROM command_runtime.runs r
            JOIN command_runtime.run_steps s ON s.run_id = r.id
            WHERE r.id = :runId AND r.status = 'interrupted'
              AND s.status = 'interrupted'
            ORDER BY s.step_index DESC
            LIMIT 1
            FOR UPDATE OF r, s
            """;

    private static final String LOCK_TASK = """
            SELECT id
            FROM command_runtime.task_executions
            WHERE step_id = :stepId AND status = 'interrupted'
            ORDER BY attempt DESC
            LIMIT 1
            FOR UPDATE
            """;

    private static final String TASK_DETAILS = """
            SELECT attempt, max_attempts, input::text AS input
            FROM command_runtime.task_executions
            WHERE id = :taskId
            """;

    private static final String RESTORE_RUN = """
            UPDATE command_runtime.runs
            SET status = 'running', error = NULL, finished_at = NULL
            WHERE id = :runId AND status = 'interrupted'
            """;

    private static final String RESTORE_STEP = """
            UPDATE command_runtime.run_steps
            SET status = 'running', finished_at = NULL
            WHERE id = :stepId AND status = 'interrupted'
            """;

    private static final String INSERT_RETRY = """
            INSERT INTO command_runtime.task_executions (
                id, step_id, attempt, max_attempts, input, status
            ) VALUES (
                :taskId, :stepId, :attempt, :maxAttempts, CAST(:input AS jsonb), 'queued'
            )
            """;
}
