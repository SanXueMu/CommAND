package com.zthcpa.command.persistence.entity.event;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "run_events", schema = "command_runtime")
public class RunEventEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false)
    private String runId;
    private String stepId;
    @Column(nullable = false)
    private String kind;
    @Column(nullable = false)
    private String actor;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> detail;
    @Column(nullable = false)
    private Instant createdAt;

    protected RunEventEntity() {
    }

    public RunEventEntity(String runId, String stepId, String kind, String actor, Map<String, Object> detail) {
        this.runId = runId;
        this.stepId = stepId;
        this.kind = kind;
        this.actor = actor;
        this.detail = detail;
        this.createdAt = Instant.now();
    }
    public Long getId() { return id; }
    public String getRunId() { return runId; }
    public String getStepId() { return stepId; }
    public String getKind() { return kind; }
    public String getActor() { return actor; }
    public Map<String, Object> getDetail() { return detail; }
    public Instant getCreatedAt() { return createdAt; }
}
