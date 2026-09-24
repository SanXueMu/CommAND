package com.zthcpa.command.persistence.entity.artifact;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "artifacts", schema = "command_runtime")
public class ArtifactEntity {
    @Id
    private String id;
    @Column(name = "run_id", nullable = false)
    private String runId;
    private String stepId;
    @Column(name = "artifact_kind", nullable = false)
    private String artifactKind;
    @Column(name = "storage_key", nullable = false)
    private String storageKey;
    private String mediaType;
    private Long sizeBytes;
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(columnDefinition = "char(64)")
    private String checksum;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> metadata;
    @Column(nullable = false)
    private Instant createdAt;

    protected ArtifactEntity() {
    }

    public ArtifactEntity(String id, String runId, String stepId, String artifactKind,
                          String storageKey, String mediaType, Long sizeBytes,
                          String checksum, Map<String, Object> metadata) {
        this.id = id;
        this.runId = runId;
        this.stepId = stepId;
        this.artifactKind = artifactKind;
        this.storageKey = storageKey;
        this.mediaType = mediaType;
        this.sizeBytes = sizeBytes;
        this.checksum = checksum;
        this.metadata = metadata;
        this.createdAt = Instant.now();
    }
    public String getId() { return id; }
    public String getRunId() { return runId; }
    public String getStepId() { return stepId; }
    public String getArtifactKind() { return artifactKind; }
    public String getStorageKey() { return storageKey; }
    public String getMediaType() { return mediaType; }
    public Long getSizeBytes() { return sizeBytes; }
    public String getChecksum() { return checksum; }
    public Map<String, Object> getMetadata() { return metadata; }
    public Instant getCreatedAt() { return createdAt; }
}
