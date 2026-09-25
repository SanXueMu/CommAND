package com.zthcpa.command.persistence.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.support.PostgresJson;
import com.zthcpa.command.persistence.step.RunStepEntity;
import com.zthcpa.command.run.TaskStatus;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Transactional
public class HibernateCleanTaskRepository implements CleanTaskRepository {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public HibernateCleanTaskRepository(EntityManager entityManager, ObjectMapper mapper) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    @Override
    public Optional<CleanTaskRow> claimNext(String workerId) {
        require(workerId, "Worker id");
        @SuppressWarnings("unchecked")
        List<Object[]> rows = entityManager.createNativeQuery("""
                SELECT t.id, t.step_id, t.attempt, t.max_attempts, t.input::text,
                       s.step_key, s.definition_id, s.definition_version
                FROM command_runtime.task_executions t
                JOIN command_runtime.run_steps s ON s.id = t.step_id
                WHERE t.status = 'queued' AND s.status = 'queued'
                ORDER BY t.created_at
                LIMIT 1
                FOR UPDATE OF t, s SKIP LOCKED
                """).getResultList();
        if (rows.isEmpty()) return Optional.empty();
        Object[] row = rows.get(0);
        int updated = entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions
                SET status = 'running', worker_id = :workerId, started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                    heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = :taskId AND status = 'queued'
                """).setParameter("workerId", workerId).setParameter("taskId", row[0]).executeUpdate();
        if (updated != 1) return Optional.empty();
        entityManager.createNativeQuery("""
                UPDATE command_runtime.run_steps SET status = 'running', started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
                WHERE id = :stepId AND status = 'queued'
                """).setParameter("stepId", row[1]).executeUpdate();
        return Optional.of(new CleanTaskRow(row[0].toString(), row[1].toString(), row[5].toString(),
                Integer.parseInt(row[2].toString()), Integer.parseInt(row[3].toString()), workerId,
                PostgresJson.read(mapper, row[4].toString()), null, null, TaskStatus.RUNNING));
    }

    @Override
    public boolean isCancellationRequested(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        Number count = (Number) entityManager.createNativeQuery("""
                SELECT COUNT(*) FROM command_runtime.task_executions
                WHERE id = :taskId AND worker_id = :workerId AND status = 'cancelled'
                """).setParameter("taskId", taskId).setParameter("workerId", workerId).getSingleResult();
        return count.longValue() > 0;
    }

    @Override
    public boolean heartbeat(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        return entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions SET heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
                """).setParameter("taskId", taskId).setParameter("workerId", workerId).executeUpdate() == 1;
    }

    @Override
    public boolean finish(String taskId, String workerId, TaskStatus status,
                          Map<String, Object> output, Map<String, Object> error) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (status == null || !status.terminal()) throw new IllegalArgumentException("Finished task must be terminal");
        return entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions
                SET status = :status, output = CAST(:output AS jsonb), error = CAST(:error AS jsonb), finished_at = CURRENT_TIMESTAMP
                WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
                """).setParameter("status", status.name().toLowerCase()).setParameter("output", "{}")
                .setParameter("error", "{}").setParameter("taskId", taskId).setParameter("workerId", workerId)
                .executeUpdate() == 1;
    }

    @Override
    public boolean requeue(String taskId, String workerId) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        return entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions
                SET status = 'queued', worker_id = NULL, heartbeat_at = NULL, attempt = attempt + 1
                WHERE id = :taskId AND worker_id = :workerId AND status = 'running' AND attempt < max_attempts
                """).setParameter("taskId", taskId).setParameter("workerId", workerId).executeUpdate() == 1;
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
