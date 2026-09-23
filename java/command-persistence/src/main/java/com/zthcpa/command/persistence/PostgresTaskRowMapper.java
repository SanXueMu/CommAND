package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresTaskRowMapper implements RowMapper<TaskRow> {
    private final ObjectMapper mapper;

    PostgresTaskRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public TaskRow mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new TaskRow(
                resultSet.getString("handle"),
                resultSet.getString("tool_id"),
                PostgresJson.read(mapper, resultSet.getString("input")),
                PostgresJson.read(mapper, resultSet.getString("output")),
                StatusValueMapper.toTaskStatus(resultSet.getString("status")),
                PostgresJson.read(mapper, resultSet.getString("error")),
                resultSet.getString("pipeline_run"),
                resultSet.getInt("step_index"),
                resultSet.getInt("attempt"),
                resultSet.getInt("max_attempts")
        );
    }
}
