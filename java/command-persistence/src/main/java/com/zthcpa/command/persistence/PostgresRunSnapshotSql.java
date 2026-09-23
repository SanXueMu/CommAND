package com.zthcpa.command.persistence;

public final class PostgresRunSnapshotSql {
    public static final String INSERT_IF_ABSENT = """
            INSERT INTO run_definition_snapshots (
                run_id, definition_kind, definition_id, definition_version,
                schema_version, checksum, document
            ) VALUES (
                :runId, :kind, :id, :definitionVersion,
                :schemaVersion, :checksum, CAST(:document AS jsonb)
            )
            ON CONFLICT (run_id, definition_kind, definition_id, definition_version) DO NOTHING
            """;

    public static final String LIST_BY_RUN = """
            SELECT run_id, definition_kind, definition_id, definition_version,
                   schema_version, checksum, document
            FROM run_definition_snapshots
            WHERE run_id = :runId
            ORDER BY definition_kind, definition_id, definition_version
            """;

    private PostgresRunSnapshotSql() {
    }
}
