package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;
import java.util.Optional;

public final class JdbcTaskRepository implements TaskRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcTaskRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public Optional<TaskRow> findByHandle(String handle) {
        return jdbc.query(PostgresTaskSql.FIND_BY_HANDLE, Map.of("handle", handle), new PostgresTaskRowMapper(mapper))
                .stream().findFirst();
    }

    @Override
    public Optional<TaskRow> claimNext(String workerId) {
        return jdbc.query(PostgresTaskSql.CLAIM_NEXT, Map.of("workerId", workerId), new PostgresTaskRowMapper(mapper))
                .stream().findFirst();
    }

    @Override
    public boolean compareAndSetStatus(String handle, TaskStatus expected, TaskStatus next) {
        Map<String, Object> params = Map.of(
                "handle", handle,
                "expectedStatus", StatusValueMapper.toDatabase(expected),
                "nextStatus", StatusValueMapper.toDatabase(next)
        );
        return jdbc.update(PostgresTaskSql.COMPARE_AND_SET_STATUS, params) == 1;
    }

    @Override
    public void requeue(String handle) {
        jdbc.update(PostgresTaskSql.REQUEUE, Map.of("handle", handle));
    }

    @Override
    public void finish(String handle, TaskStatus status, Map<String, Object> output,
                       Map<String, Object> error) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("handle", handle)
                .addValue("status", StatusValueMapper.toDatabase(status))
                .addValue("output", PostgresJson.write(mapper, output))
                .addValue("error", PostgresJson.write(mapper, error));
        jdbc.update(PostgresTaskSql.FINISH, params);
    }
}
