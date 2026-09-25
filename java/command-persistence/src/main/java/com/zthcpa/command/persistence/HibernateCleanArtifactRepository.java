package com.zthcpa.command.persistence;

import com.zthcpa.command.persistence.entity.artifact.ArtifactEntity;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Transactional
public class HibernateCleanArtifactRepository implements CleanArtifactRepository {
    private final EntityManager entityManager;

    public HibernateCleanArtifactRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public boolean register(CleanArtifact artifact) {
        if (artifact.sizeBytes() != null && artifact.sizeBytes() < 0) {
            throw new IllegalArgumentException("Artifact size must not be negative");
        }
        if (artifact.checksum() != null && !artifact.checksum().matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Artifact checksum must be lowercase SHA-256");
        }
        if (artifact.metadata() == null) {
            throw new IllegalArgumentException("Artifact metadata must not be null");
        }
        if (entityManager.find(ArtifactEntity.class, artifact.id()) != null) return false;
        entityManager.persist(new ArtifactEntity(artifact.id(), artifact.runId(), artifact.stepId(), artifact.kind(),
                artifact.storageKey(), artifact.mediaType(), artifact.sizeBytes(), artifact.checksum(), artifact.metadata()));
        return true;
    }

    @Override
    public CleanArtifact get(String artifactId) {
        ArtifactEntity entity = entityManager.find(ArtifactEntity.class, artifactId);
        return entity == null ? null : toArtifact(entity);
    }

    @Override
    public List<CleanArtifact> listByRun(String runId, int offset, int limit) {
        return list("runId", runId, offset, limit);
    }

    @Override
    public List<CleanArtifact> listByStep(String stepId, int offset, int limit) {
        return list("stepId", stepId, offset, limit);
    }

    @Override
    public boolean delete(String artifactId) {
        ArtifactEntity entity = entityManager.find(ArtifactEntity.class, artifactId);
        if (entity == null) return false;
        entityManager.remove(entity);
        return true;
    }

    private List<CleanArtifact> list(String field, String value, int offset, int limit) {
        if (offset < 0 || limit < 1 || limit > 1000) throw new IllegalArgumentException("Invalid offset or limit");
        return entityManager.createQuery("select a from ArtifactEntity a where a." + field + " = :value order by a.createdAt desc",
                        ArtifactEntity.class).setParameter("value", value).setFirstResult(offset).setMaxResults(limit)
                .getResultList().stream().map(this::toArtifact).toList();
    }

    private CleanArtifact toArtifact(ArtifactEntity entity) {
        return new CleanArtifact(entity.getId(), entity.getRunId(), entity.getStepId(), entity.getArtifactKind(),
                entity.getStorageKey(), entity.getMediaType(), entity.getSizeBytes(), entity.getChecksum(),
                entity.getMetadata(), entity.getCreatedAt());
    }
}
