package com.zthcpa.command.persistence.run;

import com.zthcpa.command.persistence.event.CleanRunEvent;
import com.zthcpa.command.persistence.event.RunEventEntity;
import com.zthcpa.command.persistence.step.CleanStepSnapshot;
import com.zthcpa.command.persistence.step.RunStepEntity;
import com.zthcpa.command.persistence.task.CleanTaskSnapshot;
import com.zthcpa.command.persistence.task.TaskExecutionEntity;
import jakarta.persistence.EntityManager;

import java.util.List;

public final class CleanRunQueryRepository {
    private final EntityManager entityManager;

    public CleanRunQueryRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public CleanRunSnapshot get(String runId) {
        require(runId, "Run id");
        List<RunEntity> runs = entityManager.createQuery(
                        "select r from RunEntity r where r.id = :runId", RunEntity.class)
                .setParameter("runId", runId).getResultList();
        if (runs.isEmpty()) return null;
        RunEntity run = runs.get(0);
        List<RunStepEntity> steps = entityManager.createQuery(
                        "select s from RunStepEntity s where s.runId = :runId order by s.stepIndex",
                        RunStepEntity.class)
                .setParameter("runId", runId).getResultList();
        return snapshot(run, steps);
    }

    public List<CleanRunSnapshot> list(int offset, int limit, String status) {
        return list(offset, limit, status, null, null);
    }

    public List<CleanRunSnapshot> list(int offset, int limit, String status, String query, String workflowId) {
        if (offset < 0 || limit < 1 || limit > 1000) throw new IllegalArgumentException("Invalid offset or limit");
        var runQuery = entityManager.createQuery(
                        "select r from RunEntity r where (:status is null or r.status = :status) " +
                                "and (:workflowId is null or r.workflowId = :workflowId) " +
                                "and (:queryText is null or lower(r.id) like :pattern or lower(r.workflowId) like :pattern) " +
                                "order by r.createdAt desc, r.id desc", RunEntity.class)
                .setParameter("status", status == null || status.isBlank() ? null : status)
                .setParameter("workflowId", workflowId == null || workflowId.isBlank() ? null : workflowId)
                .setParameter("queryText", query == null || query.isBlank() ? null : query.trim().toLowerCase())
                .setParameter("pattern", "%" + (query == null ? "" : query.trim().toLowerCase()) + "%")
                .setFirstResult(offset).setMaxResults(limit);
        return runQuery.getResultList().stream()
                .map(run -> snapshot(run, stepsFor(run.getId()))).toList();
    }

    public List<CleanRunSnapshot> list(int offset, int limit) {
        return list(offset, limit, null);
    }

    public long count(String status) {
        return count(status, null, null);
    }

    public long count(String status, String query, String workflowId) {
        return entityManager.createQuery("select count(r) from RunEntity r where (:status is null or r.status = :status) " +
                        "and (:workflowId is null or r.workflowId = :workflowId) " +
                        "and (:queryText is null or lower(r.id) like :pattern or lower(r.workflowId) like :pattern)", Long.class)
                .setParameter("status", status == null || status.isBlank() ? null : status)
                .setParameter("workflowId", workflowId == null || workflowId.isBlank() ? null : workflowId)
                .setParameter("queryText", query == null || query.isBlank() ? null : query.trim().toLowerCase())
                .setParameter("pattern", "%" + (query == null ? "" : query.trim().toLowerCase()) + "%")
                .getSingleResult();
    }

    public List<CleanRunEvent> listEvents(String runId, long afterId, int limit) {
        require(runId, "Run id");
        if (afterId < 0 || limit < 1 || limit > 1000) throw new IllegalArgumentException("Invalid afterId or limit");
        return entityManager.createQuery("""
                        select e from RunEventEntity e
                        where e.runId = :runId and e.id > :afterId order by e.id
                        """, RunEventEntity.class)
                .setParameter("runId", runId).setParameter("afterId", afterId).setMaxResults(limit)
                .getResultList().stream()
                .map(e -> new CleanRunEvent(e.getId(), e.getRunId(), e.getStepId(), e.getKind(),
                        e.getActor(), e.getDetail(), e.getCreatedAt())).toList();
    }

    private CleanRunSnapshot snapshot(RunEntity run, List<RunStepEntity> steps) {
        return new CleanRunSnapshot(run.getId(), run.getWorkflowId(), run.getWorkflowVersion(),
                run.getInput(), run.getStatus(), run.getError(), run.getCreatedAt(), run.getFinishedAt(),
                steps.stream().map(this::step).toList());
    }

    private List<RunStepEntity> stepsFor(String runId) {
        return entityManager.createQuery(
                        "select s from RunStepEntity s where s.runId = :runId order by s.stepIndex",
                        RunStepEntity.class)
                .setParameter("runId", runId).getResultList();
    }

    private CleanStepSnapshot step(RunStepEntity step) {
        List<TaskExecutionEntity> tasks = entityManager.createQuery("""
                        select t from TaskExecutionEntity t where t.stepId = :stepId
                        order by t.attempt desc
                        """, TaskExecutionEntity.class)
                .setParameter("stepId", step.getId()).setMaxResults(1).getResultList();
        CleanTaskSnapshot task = tasks.isEmpty() ? null : task(tasks.get(0));
        return new CleanStepSnapshot(step.getId(), step.getStepIndex(), step.getStepKey(),
                step.getDefinitionKind(), step.getDefinitionId(), step.getDefinitionVersion(), step.getInput(),
                step.getStatus(), step.getCreatedAt(), step.getStartedAt(), step.getFinishedAt(), task);
    }

    private CleanTaskSnapshot task(TaskExecutionEntity task) {
        return new CleanTaskSnapshot(task.getId(), task.getAttempt(), task.getMaxAttempts(), task.getWorkerId(),
                task.getInput(), task.getOutput(), task.getError(), task.getStatus(), task.getHeartbeatAt(),
                task.getCreatedAt(), task.getStartedAt(), task.getFinishedAt());
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
