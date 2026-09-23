package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.RunDefinitionSnapshot;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresRunSnapshotRowMapper implements RowMapper<RunDefinitionSnapshot> {
    private final ObjectMapper mapper;

    PostgresRunSnapshotRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public RunDefinitionSnapshot mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new RunDefinitionSnapshot(
                resultSet.getString("run_id"),
                new DefinitionKey(
                        DefinitionKind.fromValue(resultSet.getString("definition_kind")),
                        resultSet.getString("definition_id"),
                        resultSet.getInt("definition_version")
                ),
                resultSet.getInt("schema_version"),
                resultSet.getString("checksum"),
                PostgresJson.read(mapper, resultSet.getString("document"))
        );
    }
}
