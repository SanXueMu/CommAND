package com.zthcpa.command.persistence.step;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "run_steps", schema = "command_runtime")
public class RunStepEntity {
    @Id
    private String id;
    @Column(name = "run_id", nullable = false)
    private String runId;
    @Column(name = "step_index", nullable = false)
    private int stepIndex;
    @Column(name = "step_key", nullable = false)
    private String stepKey;
    @Column(name = "definition_kind", nullable = false)
    private String definitionKind;
    @Column(name = "definition_id", nullable = false)
    private String definitionId;
    @Column(name = "definition_version", nullable = false)
    private int definitionVersion;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> input;
    @Column(nullable = false)
    private String status;
    @Column(nullable = false)
    private Instant createdAt;
    private Instant startedAt;
    private Instant finishedAt;

    protected RunStepEntity() {
    }

    public RunStepEntity(String id, String runId, int stepIndex, String stepKey,
                         String definitionId, int definitionVersion, Map<String, Object> input) {
        this.id = id;
        this.runId = runId;
        this.stepIndex = stepIndex;
        this.stepKey = stepKey;
        this.definitionKind = "tool";
        this.definitionId = definitionId;
        this.definitionVersion = definitionVersion;
        this.input = input;
        this.status = "queued";
        this.createdAt = Instant.now();
    }
    public String getId() { return id; }
    public String getRunId() { return runId; }
    public int getStepIndex() { return stepIndex; }
    public String getStepKey() { return stepKey; }
    public String getDefinitionKind() { return definitionKind; }
    public String getDefinitionId() { return definitionId; }
    public int getDefinitionVersion() { return definitionVersion; }
    public Map<String, Object> getInput() { return input; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
}
