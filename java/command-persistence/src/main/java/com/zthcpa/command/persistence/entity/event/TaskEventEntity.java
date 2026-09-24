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
@Table(name = "task_events", schema = "command_runtime")
public class TaskEventEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "task_id", nullable = false)
    private String taskId;
    @Column(nullable = false)
    private String kind;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> detail;
    @Column(nullable = false)
    private Instant createdAt;

    protected TaskEventEntity() {
    }

    public TaskEventEntity(String taskId, String kind, Map<String, Object> detail) {
        this.taskId = taskId;
        this.kind = kind;
        this.detail = detail;
        this.createdAt = Instant.now();
    }
    public Long getId() { return id; }
    public String getTaskId() { return taskId; }
    public String getKind() { return kind; }
    public Map<String, Object> getDetail() { return detail; }
    public Instant getCreatedAt() { return createdAt; }
}
