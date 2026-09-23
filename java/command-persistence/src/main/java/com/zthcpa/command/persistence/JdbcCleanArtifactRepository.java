package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;

public final class JdbcCleanArtifactRepository implements CleanArtifactRepository {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcCleanArtifactRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public boolean register(CleanArtifact artifact) {
        validate(artifact);
        try {
            return jdbc.update(INSERT, parameters(artifact)) == 1;
        } catch (DuplicateKeyException exception) {
            return false;
        }
    }

    @Override
    public CleanArtifact get(String artifactId) {
        require(artifactId, "Artifact id");
        List<CleanArtifact> artifacts = jdbc.query(SELECT + " WHERE id = :id",
                Map.of("id", artifactId), this::map);
        return artifacts.isEmpty() ? null : artifacts.get(0);
    }

    @Override
    public List<CleanArtifact> listByRun(String runId, int offset, int limit) {
        return list("run_id", runId, offset, limit);
    }

    @Override
    public List<CleanArtifact> listByStep(String stepId, int offset, int limit) {
        return list("step_id", stepId, offset, limit);
    }

    @Override
    public boolean delete(String artifactId) {
        require(artifactId, "Artifact id");
        return jdbc.update("DELETE FROM command_runtime.artifacts WHERE id = :id", Map.of("id", artifactId)) == 1;
    }

    private List<CleanArtifact> list(String column, String ownerId, int offset, int limit) {
        require(ownerId, "Owner id");
        if (offset < 0 || limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("Invalid offset or limit");
        }
        return jdbc.query(SELECT + " WHERE " + column + " = :ownerId ORDER BY created_at, id OFFSET :offset LIMIT :limit",
                Map.of("ownerId", ownerId, "offset", offset, "limit", limit), this::map);
    }

    private MapSqlParameterSource parameters(CleanArtifact artifact) {
        return new MapSqlParameterSource()
                .addValue("id", artifact.id())
                .addValue("runId", artifact.runId())
                .addValue("stepId", artifact.stepId())
                .addValue("kind", artifact.kind())
                .addValue("storageKey", artifact.storageKey())
                .addValue("mediaType", artifact.mediaType())
                .addValue("sizeBytes", artifact.sizeBytes())
                .addValue("checksum", artifact.checksum())
                .addValue("metadata", PostgresJson.write(mapper, artifact.metadata() == null ? Map.of() : artifact.metadata()));
    }

    private CleanArtifact map(ResultSet resultSet, int rowNum) throws SQLException {
        Long size = resultSet.getObject("size_bytes", Long.class);
        return new CleanArtifact(
                resultSet.getString("id"), resultSet.getString("run_id"), resultSet.getString("step_id"),
                resultSet.getString("artifact_kind"), resultSet.getString("storage_key"),
                resultSet.getString("media_type"), size, resultSet.getString("checksum"),
                PostgresJson.read(mapper, resultSet.getString("metadata")),
                resultSet.getTimestamp("created_at").toInstant()
        );
    }

    private static void validate(CleanArtifact artifact) {
        if (artifact == null) {
            throw new IllegalArgumentException("Artifact must not be null");
        }
        require(artifact.id(), "Artifact id");
        require(artifact.runId(), "Run id");
        require(artifact.kind(), "Artifact kind");
        require(artifact.storageKey(), "Storage key");
        if (artifact.sizeBytes() != null && artifact.sizeBytes() < 0) {
            throw new IllegalArgumentException("Artifact size must not be negative");
        }
        if (artifact.checksum() != null && !artifact.checksum().matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Artifact checksum must be lowercase SHA-256");
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static final String SELECT = """
            SELECT id, run_id, step_id, artifact_kind, storage_key, media_type,
                   size_bytes, checksum, metadata::text AS metadata, created_at
            FROM command_runtime.artifacts
            """;

    private static final String INSERT = """
            INSERT INTO command_runtime.artifacts (
                id, run_id, step_id, artifact_kind, storage_key,
                media_type, size_bytes, checksum, metadata
            ) VALUES (
                :id, :runId, :stepId, :kind, :storageKey,
                :mediaType, :sizeBytes, :checksum, CAST(:metadata AS jsonb)
            )
            """;
}
