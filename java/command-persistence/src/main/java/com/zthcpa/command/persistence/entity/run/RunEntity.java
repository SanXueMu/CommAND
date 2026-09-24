package com.zthcpa.command.persistence.entity.run;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "runs", schema = "command_runtime")
public class RunEntity {
    @Id
    private String id;
    @Column(name = "workflow_id", nullable = false)
    private String workflowId;
    @Column(name = "workflow_version", nullable = false)
    private int workflowVersion;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> input;
    @Column(nullable = false)
    private String status;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> error;
    @Column(nullable = false)
    private Instant createdAt;
    private Instant finishedAt;

    protected RunEntity() {
    }

    public RunEntity(String id, String workflowId, int workflowVersion, Map<String, Object> input) {
        this.id = id;
        this.workflowId = workflowId;
        this.workflowVersion = workflowVersion;
        this.input = input;
        this.status = "running";
        this.createdAt = Instant.now();
    }
    public String getId() { return id; }
    public String getWorkflowId() { return workflowId; }
    public int getWorkflowVersion() { return workflowVersion; }
    public Map<String, Object> getInput() { return input; }
    public String getStatus() { return status; }
    public Map<String, Object> getError() { return error; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getFinishedAt() { return finishedAt; }
}
