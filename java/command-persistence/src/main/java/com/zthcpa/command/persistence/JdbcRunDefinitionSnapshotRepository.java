package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.RunDefinitionSnapshot;
import com.zthcpa.command.contract.RunDefinitionSnapshotRepository;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;

public final class JdbcRunDefinitionSnapshotRepository implements RunDefinitionSnapshotRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcRunDefinitionSnapshotRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public void saveIfAbsent(String runId, DefinitionDocument definition) {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("runId", runId)
                .addValue("kind", definition.key().kind().value())
                .addValue("id", definition.key().id())
                .addValue("definitionVersion", definition.key().version())
                .addValue("schemaVersion", definition.schemaVersion())
                .addValue("checksum", definition.checksum())
                .addValue("document", PostgresJson.write(mapper, definition.content()));
        jdbc.update(PostgresRunSnapshotSql.INSERT_IF_ABSENT, parameters);
    }

    @Override
    public List<RunDefinitionSnapshot> listByRun(String runId) {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        return jdbc.query(
                PostgresRunSnapshotSql.LIST_BY_RUN,
                new MapSqlParameterSource("runId", runId),
                new PostgresRunSnapshotRowMapper(mapper)
        );
    }
}
