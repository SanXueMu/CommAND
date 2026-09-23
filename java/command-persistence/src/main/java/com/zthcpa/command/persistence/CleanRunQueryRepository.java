package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class CleanRunQueryRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public CleanRunQueryRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public CleanRunSnapshot get(String runId) {
        require(runId, "Run id");
        List<CleanRunSnapshot> runs = jdbc.query(RUN_DETAIL, Map.of("runId", runId), this::mapRun);
        if (runs.isEmpty()) {
            return null;
        }
        CleanRunSnapshot run = runs.get(0);
        List<CleanStepSnapshot> steps = jdbc.query(STEPS, Map.of("runId", runId), this::mapStep);
        return new CleanRunSnapshot(
                run.id(), run.workflowId(), run.workflowVersion(), run.input(), run.status(), run.error(),
                run.createdAt(), run.finishedAt(), steps
        );
    }

    public List<CleanRunSnapshot> list(int offset, int limit) {
        if (offset < 0 || limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("Invalid offset or limit");
        }
        return jdbc.query(RUN_LIST, Map.of("offset", offset, "limit", limit), this::mapRun);
    }

    public List<CleanRunEvent> listEvents(String runId, long afterId, int limit) {
        require(runId, "Run id");
        if (afterId < 0 || limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("Invalid afterId or limit");
        }
        return jdbc.query(EVENTS, new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("afterId", afterId)
                .addValue("limit", limit), new PostgresCleanRunEventRowMapper(mapper));
    }

    private CleanRunSnapshot mapRun(ResultSet resultSet, int rowNum) throws SQLException {
        return new CleanRunSnapshot(
                resultSet.getString("id"),
                resultSet.getString("workflow_id"),
                resultSet.getInt("workflow_version"),
                PostgresJson.read(mapper, resultSet.getString("input")),
                resultSet.getString("status"),
                PostgresJson.read(mapper, resultSet.getString("error")),
                resultSet.getTimestamp("created_at").toInstant(),
                timestamp(resultSet, "finished_at"),
                List.of()
        );
    }

    private CleanStepSnapshot mapStep(ResultSet resultSet, int rowNum) throws SQLException {
        return new CleanStepSnapshot(
                resultSet.getString("id"),
                resultSet.getInt("step_index"),
                resultSet.getString("step_key"),
                resultSet.getString("definition_kind"),
                resultSet.getString("definition_id"),
                resultSet.getInt("definition_version"),
                PostgresJson.read(mapper, resultSet.getString("input")),
                resultSet.getString("status"),
                resultSet.getTimestamp("created_at").toInstant(),
                timestamp(resultSet, "started_at"),
                timestamp(resultSet, "finished_at"),
                mapTask(resultSet)
        );
    }

    private CleanTaskSnapshot mapTask(ResultSet resultSet) throws SQLException {
        String taskId = resultSet.getString("task_id");
        if (taskId == null) {
            return null;
        }
        return new CleanTaskSnapshot(
                taskId,
                resultSet.getInt("attempt"),
                resultSet.getInt("max_attempts"),
                resultSet.getString("worker_id"),
                PostgresJson.read(mapper, resultSet.getString("task_input")),
                PostgresJson.read(mapper, resultSet.getString("output")),
                PostgresJson.read(mapper, resultSet.getString("task_error")),
                resultSet.getString("task_status"),
                timestamp(resultSet, "heartbeat_at"),
                timestamp(resultSet, "task_created_at"),
                timestamp(resultSet, "task_started_at"),
                timestamp(resultSet, "task_finished_at")
        );
    }

    private static Instant timestamp(ResultSet resultSet, String column) throws SQLException {
        var timestamp = resultSet.getTimestamp(column);
        return timestamp == null ? null : timestamp.toInstant();
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static final String RUN_DETAIL = """
            SELECT id, workflow_id, workflow_version, input::text AS input,
                   status, error::text AS error, created_at, finished_at
            FROM command_runtime.runs
            WHERE id = :runId
            """;

    private static final String RUN_LIST = """
            SELECT id, workflow_id, workflow_version, input::text AS input,
                   status, error::text AS error, created_at, finished_at
            FROM command_runtime.runs
            ORDER BY created_at DESC, id DESC
            OFFSET :offset LIMIT :limit
            """;

    private static final String STEPS = """
            SELECT s.id, s.step_index, s.step_key, s.definition_kind,
                   s.definition_id, s.definition_version, s.input::text AS input,
                   s.status, s.created_at, s.started_at, s.finished_at,
                   t.id AS task_id, t.attempt, t.max_attempts, t.worker_id,
                   t.input::text AS task_input, t.output::text AS output,
                   t.error::text AS task_error, t.status AS task_status,
                   t.heartbeat_at, t.created_at AS task_created_at,
                   t.started_at AS task_started_at, t.finished_at AS task_finished_at
            FROM command_runtime.run_steps s
            LEFT JOIN LATERAL (
                SELECT *
                FROM command_runtime.task_executions candidate
                WHERE candidate.step_id = s.id
                ORDER BY candidate.attempt DESC
                LIMIT 1
            ) t ON true
            WHERE s.run_id = :runId
            ORDER BY s.step_index
            """;

    private static final String EVENTS = """
            SELECT id, run_id, step_id, kind, actor, detail::text AS detail, created_at
            FROM command_runtime.run_events
            WHERE run_id = :runId AND id > :afterId
            ORDER BY id
            LIMIT :limit
            """;
}
