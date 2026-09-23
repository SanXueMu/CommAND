package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

final class PostgresDefinitionRowMapper implements RowMapper<DefinitionDocument> {
    private final ObjectMapper mapper;

    PostgresDefinitionRowMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public DefinitionDocument mapRow(ResultSet resultSet, int rowNum) throws SQLException {
        return new DefinitionDocument(
                new DefinitionKey(
                        DefinitionKind.fromValue(resultSet.getString("kind")),
                        resultSet.getString("id"),
                        resultSet.getInt("definition_version")
                ),
                resultSet.getInt("schema_version"),
                DefinitionStatus.fromValue(resultSet.getString("status")),
                PostgresJson.read(mapper, resultSet.getString("document")),
                resultSet.getString("checksum"),
                "postgresql:command_definitions"
        );
    }
}
