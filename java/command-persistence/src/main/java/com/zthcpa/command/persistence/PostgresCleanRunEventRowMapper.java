package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresCleanRunEventRowMapper implements RowMapper<CleanRunEvent> {
    private final ObjectMapper mapper;

    PostgresCleanRunEventRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CleanRunEvent mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new CleanRunEvent(
                resultSet.getLong("id"),
                resultSet.getString("run_id"),
                resultSet.getString("step_id"),
                resultSet.getString("kind"),
                resultSet.getString("actor"),
                PostgresJson.read(mapper, resultSet.getString("detail")),
                resultSet.getTimestamp("created_at").toInstant()
        );
    }
}
