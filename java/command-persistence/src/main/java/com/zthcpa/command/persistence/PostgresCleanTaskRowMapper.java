package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresCleanTaskRowMapper implements RowMapper<CleanTaskRow> {
    private final ObjectMapper mapper;

    PostgresCleanTaskRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CleanTaskRow mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new CleanTaskRow(
                resultSet.getString("id"),
                resultSet.getString("step_id"),
                resultSet.getString("tool_id"),
                resultSet.getInt("attempt"),
                resultSet.getInt("max_attempts"),
                resultSet.getString("worker_id"),
                PostgresJson.read(mapper, resultSet.getString("input")),
                PostgresJson.read(mapper, resultSet.getString("output")),
                PostgresJson.read(mapper, resultSet.getString("error")),
                TaskStatus.valueOf(resultSet.getString("status").toUpperCase())
        );
    }
}
