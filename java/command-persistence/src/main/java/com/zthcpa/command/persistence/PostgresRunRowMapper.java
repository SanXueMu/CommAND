package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.RunStatus;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresRunRowMapper implements RowMapper<RunRow> {
    private final ObjectMapper mapper;

    PostgresRunRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public RunRow mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new RunRow(
                resultSet.getString("id"),
                resultSet.getString("pipeline_id"),
                PostgresJson.read(mapper, resultSet.getString("input")),
                StatusValueMapper.toRunStatus(resultSet.getString("status")),
                PostgresJson.read(mapper, resultSet.getString("error")),
                resultSet.getTimestamp("created_at").toInstant(),
                resultSet.getTimestamp("finished_at") == null
                        ? null : resultSet.getTimestamp("finished_at").toInstant()
        );
    }
}
