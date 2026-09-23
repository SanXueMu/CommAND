package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;
import java.util.Map;

public final class JdbcCleanEventRepository implements CleanEventRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcCleanEventRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public long appendRunEvent(String runId, String stepId, String kind, String actor,
                               Map<String, Object> detail) {
        require(runId, "Run id");
        require(kind, "Event kind");
        require(actor, "Event actor");
        return jdbc.queryForObject(CleanEventSql.INSERT_RUN, new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("stepId", stepId)
                .addValue("kind", kind)
                .addValue("actor", actor)
                .addValue("detail", PostgresJson.write(mapper, detail == null ? Map.of() : detail)),
                Long.class);
    }

    @Override
    public long appendTaskEvent(String taskId, String kind, Map<String, Object> detail) {
        require(taskId, "Task id");
        require(kind, "Event kind");
        return jdbc.queryForObject(CleanEventSql.INSERT_TASK, new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("kind", kind)
                .addValue("detail", PostgresJson.write(mapper, detail == null ? Map.of() : detail)),
                Long.class);
    }

    @Override
    public List<CleanRunEvent> listRunEvents(String runId, long afterId, int limit) {
        return jdbc.query(CleanEventSql.LIST_RUN,
                parameters(runId, afterId, limit), new PostgresCleanRunEventRowMapper(mapper));
    }

    @Override
    public List<CleanTaskEvent> listTaskEvents(String taskId, long afterId, int limit) {
        return jdbc.query(CleanEventSql.LIST_TASK,
                parameters(taskId, afterId, limit), new PostgresCleanTaskEventRowMapper(mapper));
    }

    private static Map<String, Object> parameters(String ownerId, long afterId, int limit) {
        require(ownerId, "Event owner id");
        if (afterId < 0) {
            throw new IllegalArgumentException("afterId must not be negative");
        }
        if (limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("limit must be between 1 and 1000");
        }
        return Map.of("runId", ownerId, "taskId", ownerId, "afterId", afterId, "limit", limit);
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
