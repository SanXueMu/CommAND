package com.zthcpa.command.persistence.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.support.PostgresJson;
import com.zthcpa.command.persistence.event.RunEventEntity;
import com.zthcpa.command.persistence.event.TaskEventEntity;
import com.zthcpa.command.persistence.task.TaskExecutionEntity;
import com.zthcpa.command.run.PipelineExecutionIdentifiers;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;

@Transactional
public class CleanRecoveryRepository {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public CleanRecoveryRepository(EntityManager entityManager, ObjectMapper mapper) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    public boolean recoverInterruptedRun(String runId) {
        require(runId, "Run id");
        @SuppressWarnings("unchecked")
        List<Object[]> rows = entityManager.createNativeQuery("""
                SELECT s.id, s.step_index, t.id, t.attempt, t.max_attempts, t.input::text
                FROM command_runtime.run_steps s
                JOIN command_runtime.task_executions t ON t.step_id = s.id
                WHERE s.run_id=:runId AND s.status='interrupted' AND t.status='interrupted'
                ORDER BY s.step_index DESC, t.attempt DESC LIMIT 1
                FOR UPDATE OF s, t
                """).setParameter("runId", runId).getResultList();
        if (rows.isEmpty()) return false;
        Object[] row = rows.get(0);
         int stepIndex = number(row[1]);
         int attempt = number(row[3]);
         int maxAttempts = number(row[4]);
        if (attempt >= maxAttempts) return false;
         String stepId = row[0].toString();
        restore(runId, stepId);
         String retryId = PipelineExecutionIdentifiers.recoveryTaskId(runId, stepIndex, attempt + 1);
         entityManager.persist(new TaskExecutionEntity(retryId, stepId, attempt + 1, maxAttempts,
                 PostgresJson.read(mapper, row[5].toString())));
        appendEvents(runId, stepId, retryId, "run.recovered", "task.requeued", attempt + 1);
        return true;
    }

    public int recoverStaleTasks(Instant staleBefore, int limit) {
        if (staleBefore == null) throw new IllegalArgumentException("staleBefore must not be null");
        if (limit <= 0) throw new IllegalArgumentException("limit must be positive");
        @SuppressWarnings("unchecked")
        List<Object[]> rows = entityManager.createNativeQuery("""
                SELECT t.id, t.step_id, s.run_id, s.step_index, t.attempt, t.max_attempts, t.input::text
                FROM command_runtime.task_executions t
                JOIN command_runtime.run_steps s ON s.id=t.step_id
                JOIN command_runtime.runs r ON r.id=s.run_id
                WHERE t.status='running' AND s.status='running' AND r.status='running'
                  AND t.heartbeat_at < :staleBefore
                ORDER BY t.heartbeat_at, t.created_at LIMIT :limit
                FOR UPDATE OF t, s, r SKIP LOCKED
                """).setParameter("staleBefore", Timestamp.from(staleBefore))
                .setParameter("limit", limit).getResultList();
        int recovered = 0;
        for (Object[] row : rows) {
            int stepIndex = number(row[3]);
            int attempt = number(row[4]);
            int maxAttempts = number(row[5]);
            if (attempt >= maxAttempts) continue;
            String taskId = row[0].toString();
            String stepId = row[1].toString();
            String runId = row[2].toString();
            markInterrupted(taskId, stepId, runId);
            restore(runId, stepId);
            String retryId = PipelineExecutionIdentifiers.recoveryTaskId(runId, stepIndex, attempt + 1);
            entityManager.persist(new TaskExecutionEntity(retryId, stepId, attempt + 1, maxAttempts,
                    PostgresJson.read(mapper, row[6].toString())));
            appendEvents(runId, stepId, retryId, "run.stale_recovered", "task.stale_recovered", attempt + 1);
            recovered++;
        }
        return recovered;
    }

    private void restore(String runId, String stepId) {
        entityManager.createNativeQuery("UPDATE command_runtime.runs SET status='running', error=NULL, finished_at=NULL WHERE id=:id")
                .setParameter("id", runId).executeUpdate();
        entityManager.createNativeQuery("UPDATE command_runtime.run_steps SET status='running', finished_at=NULL WHERE id=:id")
                .setParameter("id", stepId).executeUpdate();
    }

    private void markInterrupted(String taskId, String stepId, String runId) {
        entityManager.createNativeQuery("UPDATE command_runtime.task_executions SET status='interrupted', finished_at=CURRENT_TIMESTAMP WHERE id=:id AND status='running'")
                .setParameter("id", taskId).executeUpdate();
        entityManager.createNativeQuery("UPDATE command_runtime.run_steps SET status='interrupted', finished_at=CURRENT_TIMESTAMP WHERE id=:id AND status='running'")
                .setParameter("id", stepId).executeUpdate();
        entityManager.createNativeQuery("UPDATE command_runtime.runs SET status='interrupted', finished_at=CURRENT_TIMESTAMP WHERE id=:id AND status='running'")
                .setParameter("id", runId).executeUpdate();
    }

    private void appendEvents(String runId, String stepId, String taskId, String runKind, String taskKind, int attempt) {
        entityManager.persist(new TaskEventEntity(taskId, taskKind, Map.of("attempt", attempt)));
        entityManager.persist(new RunEventEntity(runId, stepId, runKind, "system", Map.of("task_id", taskId)));
    }

    private static int number(Object value) { return ((Number) value).intValue(); }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
