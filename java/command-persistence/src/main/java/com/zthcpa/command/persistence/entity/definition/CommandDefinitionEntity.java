package com.zthcpa.command.persistence.entity.definition;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "command_definitions", schema = "command_runtime")
@IdClass(CommandDefinitionId.class)
public class CommandDefinitionEntity {
    @Id
    private String kind;
    @Id
    private String id;
    @Id
    @Column(name = "definition_version")
    private int definitionVersion;
    @Column(name = "schema_version", nullable = false)
    private int schemaVersion;
    @Column(nullable = false)
    private String status;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> document;
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, columnDefinition = "char(64)")
    private String checksum;
    @Column(nullable = false)
    private String owner;
    @Column(nullable = false)
    private Instant createdAt;
    @Column(nullable = false)
    private Instant updatedAt;

    protected CommandDefinitionEntity() {
    }

    public CommandDefinitionEntity(
            String kind,
            String id,
            int definitionVersion,
            int schemaVersion,
            String status,
            Map<String, Object> document,
            String checksum,
            String owner,
            Instant createdAt,
            Instant updatedAt
    ) {
        this.kind = kind;
        this.id = id;
        this.definitionVersion = definitionVersion;
        this.schemaVersion = schemaVersion;
        this.status = status;
        this.document = document;
        this.checksum = checksum;
        this.owner = owner;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public String getKind() { return kind; }
    public String getId() { return id; }
    public int getDefinitionVersion() { return definitionVersion; }
    public int getSchemaVersion() { return schemaVersion; }
    public String getStatus() { return status; }
    public Map<String, Object> getDocument() { return document; }
    public String getChecksum() { return checksum; }
}
