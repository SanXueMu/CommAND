package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionRepository;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;

public final class JdbcDefinitionRepository implements DefinitionRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcDefinitionRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public void saveIfAbsent(DefinitionDocument definition) {
        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("id", definition.key().id())
                .addValue("kind", definition.key().kind().value())
                .addValue("definitionVersion", definition.key().version())
                .addValue("schemaVersion", definition.schemaVersion())
                .addValue("status", definition.status().value())
                .addValue("document", PostgresJson.write(mapper, definition.content()))
                .addValue("checksum", definition.checksum())
                .addValue("owner", "command");
        jdbc.update(PostgresDefinitionSql.INSERT_IF_ABSENT, parameters);
    }

    @Override
    public List<DefinitionDocument> list() {
        return jdbc.query(PostgresDefinitionSql.LIST, new PostgresDefinitionRowMapper(mapper));
    }
}
