package com.zthcpa.command.persistence.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

import java.time.OffsetDateTime;

@Entity
@Immutable
@Table(name = "command_definitions", schema = "command_runtime")
@IdClass(CommandDefinitionId.class)
public class CommandDefinitionEntity {
    @Id
    @Column(name = "kind", nullable = false)
    private String kind;

    @Id
    @Column(name = "id", nullable = false)
    private String id;

    @Id
    @Column(name = "definition_version", nullable = false)
    private int definitionVersion;

    @Column(name = "schema_version", nullable = false)
    private int schemaVersion;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "document", nullable = false, columnDefinition = "jsonb")
    private String document;

    @Column(name = "checksum", nullable = false)
    private String checksum;

    @Column(name = "owner", nullable = false)
    private String owner;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected CommandDefinitionEntity() {
    }

    public String getKind() {
        return kind;
    }

    public String getId() {
        return id;
    }

    public int getDefinitionVersion() {
        return definitionVersion;
    }

    public int getSchemaVersion() {
        return schemaVersion;
    }

    public String getStatus() {
        return status;
    }

    public String getDocument() {
        return document;
    }

    public String getChecksum() {
        return checksum;
    }
}
