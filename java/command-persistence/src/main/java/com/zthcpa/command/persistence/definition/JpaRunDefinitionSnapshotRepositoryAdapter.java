package com.zthcpa.command.persistence.definition;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.RunDefinitionSnapshot;
import com.zthcpa.command.contract.RunDefinitionSnapshotRepository;
import com.zthcpa.command.persistence.run.RunDefinitionSnapshotEntity;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Transactional
public class JpaRunDefinitionSnapshotRepositoryAdapter implements RunDefinitionSnapshotRepository {
    private final EntityManager entityManager;

    public JpaRunDefinitionSnapshotRepositoryAdapter(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public void saveIfAbsent(String runId, DefinitionDocument definition) {
        var key = definition.key();
        Number count = (Number) entityManager.createNativeQuery("""
                SELECT COUNT(*) FROM command_runtime.run_definition_snapshots
                WHERE run_id=:runId AND definition_kind=:kind AND definition_id=:id AND definition_version=:version
                """).setParameter("runId", runId).setParameter("kind", key.kind().value())
                .setParameter("id", key.id()).setParameter("version", key.version()).getSingleResult();
        if (count.longValue() > 0) return;
        entityManager.persist(new RunDefinitionSnapshotEntity(runId, key.kind().value(), key.id(), key.version(),
                definition.schemaVersion(), definition.checksum(), definition.content()));
    }

    @Override
    public List<RunDefinitionSnapshot> listByRun(String runId) {
        return entityManager.createQuery("select s from RunDefinitionSnapshotEntity s where s.runId=:runId order by s.definitionKind, s.definitionId, s.definitionVersion",
                        RunDefinitionSnapshotEntity.class).setParameter("runId", runId).getResultList().stream()
                .map(s -> new RunDefinitionSnapshot(s.getRunId(),
                        new com.zthcpa.command.contract.DefinitionKey(
                                com.zthcpa.command.contract.DefinitionKind.fromValue(s.getDefinitionKind()),
                                s.getDefinitionId(), s.getDefinitionVersion()), s.getSchemaVersion(), s.getChecksum(), s.getDocument()))
                .toList();
    }
}
