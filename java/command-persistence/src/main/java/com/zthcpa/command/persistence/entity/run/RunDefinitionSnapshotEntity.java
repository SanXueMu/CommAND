package com.zthcpa.command.persistence.entity.run;

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
@Table(name = "run_definition_snapshots", schema = "command_runtime")
@IdClass(RunDefinitionSnapshotId.class)
public class RunDefinitionSnapshotEntity {
    @Id
    @Column(name = "run_id")
    private String runId;
    @Id
    @Column(name = "definition_kind")
    private String definitionKind;
    @Id
    @Column(name = "definition_id")
    private String definitionId;
    @Id
    @Column(name = "definition_version")
    private int definitionVersion;
    @Column(name = "schema_version", nullable = false)
    private int schemaVersion;
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, columnDefinition = "char(64)")
    private String checksum;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> document;
    @Column(nullable = false)
    private Instant createdAt;

    protected RunDefinitionSnapshotEntity() {
    }

    public RunDefinitionSnapshotEntity(String runId, String kind, String id, int version,
                                       int schemaVersion, String checksum, Map<String, Object> document) {
        this.runId = runId;
        this.definitionKind = kind;
        this.definitionId = id;
        this.definitionVersion = version;
        this.schemaVersion = schemaVersion;
        this.checksum = checksum;
        this.document = document;
        this.createdAt = Instant.now();
    }

    public String getRunId() { return runId; }
    public String getDefinitionKind() { return definitionKind; }
    public String getDefinitionId() { return definitionId; }
    public int getDefinitionVersion() { return definitionVersion; }
    public int getSchemaVersion() { return schemaVersion; }
    public String getChecksum() { return checksum; }
    public Map<String, Object> getDocument() { return document; }
    public Instant getCreatedAt() { return createdAt; }
}
