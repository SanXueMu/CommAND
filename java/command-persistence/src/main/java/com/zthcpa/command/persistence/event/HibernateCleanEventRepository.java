package com.zthcpa.command.persistence.event;

import jakarta.persistence.EntityManager;

import java.util.List;
import java.util.Map;

public final class HibernateCleanEventRepository implements CleanEventRepository {
    private final EntityManager entityManager;

    public HibernateCleanEventRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public long appendRunEvent(String runId, String stepId, String kind, String actor,
                               Map<String, Object> detail) {
        require(runId, "Run id");
        require(kind, "Event kind");
        require(actor, "Event actor");
        RunEventEntity event = new RunEventEntity(runId, stepId, kind, actor,
                detail == null ? Map.of() : detail);
        entityManager.persist(event);
        entityManager.flush();
        return event.getId();
    }

    @Override
    public long appendTaskEvent(String taskId, String kind, Map<String, Object> detail) {
        require(taskId, "Task id");
        require(kind, "Event kind");
        TaskEventEntity event = new TaskEventEntity(taskId, kind, detail == null ? Map.of() : detail);
        entityManager.persist(event);
        entityManager.flush();
        return event.getId();
    }

    @Override
    public List<CleanRunEvent> listRunEvents(String runId, long afterId, int limit) {
        validate(runId, afterId, limit);
        return entityManager.createQuery("""
                        select e from RunEventEntity e
                        where e.runId = :runId and e.id > :afterId order by e.id
                        """, RunEventEntity.class)
                .setParameter("runId", runId).setParameter("afterId", afterId)
                .setMaxResults(limit).getResultList().stream()
                .map(e -> new CleanRunEvent(e.getId(), e.getRunId(), e.getStepId(), e.getKind(),
                        e.getActor(), e.getDetail(), e.getCreatedAt())).toList();
    }

    @Override
    public List<CleanTaskEvent> listTaskEvents(String taskId, long afterId, int limit) {
        validate(taskId, afterId, limit);
        return entityManager.createQuery("""
                        select e from TaskEventEntity e
                        where e.taskId = :taskId and e.id > :afterId order by e.id
                        """, TaskEventEntity.class)
                .setParameter("taskId", taskId).setParameter("afterId", afterId)
                .setMaxResults(limit).getResultList().stream()
                .map(e -> new CleanTaskEvent(e.getId(), e.getTaskId(), e.getKind(),
                        e.getDetail(), e.getCreatedAt())).toList();
    }

    private static void validate(String ownerId, long afterId, int limit) {
        require(ownerId, "Event owner id");
        if (afterId < 0 || limit < 1 || limit > 1000) {
            throw new IllegalArgumentException("Invalid event cursor or limit");
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
