package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.RunStatus;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.Map;
import java.util.Optional;

public final class JdbcRunRepository implements RunRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcRunRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public Optional<RunRow> findById(String runId) {
        return jdbc.query(PostgresRunSql.FIND_BY_ID, Map.of("runId", runId), new PostgresRunRowMapper(mapper))
                .stream().findFirst();
    }

    @Override
    public boolean compareAndSetStatus(String runId, RunStatus expected, RunStatus next) {
        Map<String, Object> params = Map.of(
                "runId", runId,
                "expectedStatus", StatusValueMapper.toDatabase(expected),
                "nextStatus", StatusValueMapper.toDatabase(next)
        );
        return jdbc.update(PostgresRunSql.COMPARE_AND_SET_STATUS, params) == 1;
    }

    @Override
    public void finish(String runId, RunStatus status, Map<String, Object> error) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("status", StatusValueMapper.toDatabase(status))
                .addValue("error", PostgresJson.write(mapper, error));
        jdbc.update(PostgresRunSql.FINISH, params);
    }
}
