package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;
import java.util.Optional;

public final class JdbcCleanTaskRepository implements CleanTaskRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcCleanTaskRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public Optional<CleanTaskRow> claimNext(String workerId) {
        require(workerId, "Worker id");
        return jdbc.query(CleanTaskSql.CLAIM_NEXT, Map.of("workerId", workerId),
                new PostgresCleanTaskRowMapper(mapper)).stream().findFirst();
    }

    @Override
    public boolean isCancellationRequested(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        return Boolean.TRUE.equals(jdbc.queryForObject(
                CleanTaskSql.CANCELLATION_REQUESTED,
                Map.of("taskId", taskId, "workerId", workerId),
                Boolean.class
        ));
    }

    @Override
    public boolean heartbeat(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        return jdbc.update(CleanTaskSql.HEARTBEAT,
                Map.of("taskId", taskId, "workerId", workerId)) == 1;
    }

    @Override
    public boolean finish(String taskId, String workerId, TaskStatus status,
                          Map<String, Object> output, Map<String, Object> error) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (!status.terminal()) {
            throw new IllegalArgumentException("Finished task must be terminal");
        }
        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("taskId", taskId)
                .addValue("workerId", workerId)
                .addValue("status", status.name().toLowerCase())
                .addValue("output", PostgresJson.write(mapper, output))
                .addValue("error", PostgresJson.write(mapper, error));
        return jdbc.update(CleanTaskSql.FINISH, parameters) == 1;
    }

    @Override
    public boolean requeue(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        return jdbc.update(CleanTaskSql.REQUEUE,
                Map.of("taskId", taskId, "workerId", workerId)) == 1;
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
