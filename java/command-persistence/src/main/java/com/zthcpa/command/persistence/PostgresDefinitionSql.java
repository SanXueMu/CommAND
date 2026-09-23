package com.zthcpa.command.persistence;

public final class PostgresDefinitionSql {
    public static final String INSERT_IF_ABSENT = """
            INSERT INTO command_definitions (
                id, kind, definition_version, schema_version, status,
                document, checksum, owner
            ) VALUES (
                :id, :kind, :definitionVersion, :schemaVersion, :status,
                CAST(:document AS jsonb), :checksum, :owner
            )
            ON CONFLICT (kind, id, definition_version) DO NOTHING
            """;

    public static final String LIST = """
            SELECT id, kind, definition_version, schema_version, status,
                   document, checksum
            FROM command_definitions
            ORDER BY kind, id, definition_version
            """;

    private PostgresDefinitionSql() {
    }
}
