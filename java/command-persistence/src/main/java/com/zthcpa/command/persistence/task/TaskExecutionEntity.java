package com.zthcpa.command.persistence.task;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "task_executions", schema = "command_runtime")
public class TaskExecutionEntity {
    @Id
    private String id;
    @Column(name = "step_id", nullable = false)
    private String stepId;
    @Column(nullable = false)
    private int attempt;
    @Column(name = "max_attempts", nullable = false)
    private int maxAttempts;
    private String workerId;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> input;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> output;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> error;
    @Column(nullable = false)
    private String status;
    private Instant heartbeatAt;
    @Column(nullable = false)
    private Instant createdAt;
    private Instant startedAt;
    private Instant finishedAt;

    protected TaskExecutionEntity() {
    }

    public TaskExecutionEntity(String id, String stepId, int maxAttempts, Map<String, Object> input) {
        this(id, stepId, 1, maxAttempts, input);
    }

    public TaskExecutionEntity(String id, String stepId, int attempt, int maxAttempts,
                               Map<String, Object> input) {
        this.id = id;
        this.stepId = stepId;
        if (attempt < 1) {
            throw new IllegalArgumentException("Attempt must be positive");
        }
        this.attempt = attempt;
        this.maxAttempts = maxAttempts;
        this.input = input;
        this.status = "queued";
        this.createdAt = Instant.now();
    }
    public String getId() { return id; }
    public String getStepId() { return stepId; }
    public int getAttempt() { return attempt; }
    public int getMaxAttempts() { return maxAttempts; }
    public String getWorkerId() { return workerId; }
    public Map<String, Object> getInput() { return input; }
    public Map<String, Object> getOutput() { return output; }
    public Map<String, Object> getError() { return error; }
    public String getStatus() { return status; }
    public Instant getHeartbeatAt() { return heartbeatAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
}
