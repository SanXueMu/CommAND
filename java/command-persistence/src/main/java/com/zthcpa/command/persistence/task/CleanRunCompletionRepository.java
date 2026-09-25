package com.zthcpa.command.persistence.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.support.PostgresJson;
import com.zthcpa.command.persistence.event.RunEventEntity;
import com.zthcpa.command.persistence.event.TaskEventEntity;
import com.zthcpa.command.run.RunStatus;
import com.zthcpa.command.run.TaskStatus;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Transactional
public class CleanRunCompletionRepository {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public CleanRunCompletionRepository(EntityManager entityManager, ObjectMapper mapper) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    public boolean completeTask(String taskId, String workerId, TaskStatus status,
                                Map<String, Object> output, Map<String, Object> error) {
        validate(taskId, workerId, status);
        return close(taskId, workerId, status, output, error);
    }

    public boolean failTask(String taskId, String workerId, TaskStatus status, Map<String, Object> error) {
        if (status != TaskStatus.FAILED && status != TaskStatus.FAILED_REVIEW) {
            throw new IllegalArgumentException("Failure status must be FAILED or FAILED_REVIEW");
        }
        validate(taskId, workerId, status);
        return close(taskId, workerId, status, Map.of(), error);
    }

    public boolean stopTask(String taskId, String workerId, TaskStatus status, Map<String, Object> detail) {
        if (status != TaskStatus.CANCELLED && status != TaskStatus.INTERRUPTED) {
            throw new IllegalArgumentException("Stop status must be CANCELLED or INTERRUPTED");
        }
        validate(taskId, workerId, status);
        return close(taskId, workerId, status, Map.of(), detail);
    }

    private boolean close(String taskId, String workerId, TaskStatus taskStatus,
                          Map<String, Object> output, Map<String, Object> error) {
        int updated = entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions
                SET status=:status, output=CAST(:output AS jsonb), error=CAST(:error AS jsonb), finished_at=CURRENT_TIMESTAMP
                WHERE id=:taskId AND worker_id=:workerId AND status='running'
                """).setParameter("status", taskStatus.name().toLowerCase())
                .setParameter("output", PostgresJson.write(mapper, output == null ? Map.of() : output))
                .setParameter("error", PostgresJson.write(mapper, error == null ? Map.of() : error))
                .setParameter("taskId", taskId).setParameter("workerId", workerId).executeUpdate();
        if (updated != 1) return false;
        Object stepId = entityManager.createNativeQuery("SELECT step_id FROM command_runtime.task_executions WHERE id=:id")
                .setParameter("id", taskId).getSingleResult();
        Object runId = entityManager.createNativeQuery("SELECT run_id FROM command_runtime.run_steps WHERE id=:id")
                .setParameter("id", stepId).getSingleResult();
        String stepStatus = taskStatus == TaskStatus.SUCCEEDED ? "succeeded"
                : taskStatus == TaskStatus.CANCELLED ? "cancelled"
                : taskStatus == TaskStatus.INTERRUPTED ? "interrupted" : "failed";
        String runStatus = taskStatus == TaskStatus.FAILED_REVIEW ? "failed_review" : taskStatus.name().toLowerCase();
        entityManager.createNativeQuery("UPDATE command_runtime.run_steps SET status=:status, finished_at=CURRENT_TIMESTAMP WHERE id=:id")
                .setParameter("status", stepStatus).setParameter("id", stepId).executeUpdate();
        entityManager.createNativeQuery("UPDATE command_runtime.runs SET status=:status, error=CAST(:error AS jsonb), finished_at=CURRENT_TIMESTAMP WHERE id=:id")
                .setParameter("status", runStatus).setParameter("error", PostgresJson.write(mapper, error == null ? Map.of() : error))
                .setParameter("id", runId).executeUpdate();
        entityManager.persist(new TaskEventEntity(taskId, "task." + taskStatus.name().toLowerCase(), error == null ? Map.of() : error));
        entityManager.persist(new RunEventEntity(runId.toString(), stepId.toString(), "run." + runStatus, "system", error == null ? Map.of() : error));
        return true;
    }

    private static void validate(String taskId, String workerId, TaskStatus status) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (status == null || !status.terminal()) throw new IllegalArgumentException("Task status must be terminal");
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
