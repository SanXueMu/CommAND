package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresCleanTaskEventRowMapper implements RowMapper<CleanTaskEvent> {
    private final ObjectMapper mapper;

    PostgresCleanTaskEventRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CleanTaskEvent mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new CleanTaskEvent(
                resultSet.getLong("id"),
                resultSet.getString("task_id"),
                resultSet.getString("kind"),
                PostgresJson.read(mapper, resultSet.getString("detail")),
                resultSet.getTimestamp("created_at").toInstant()
        );
    }
}
