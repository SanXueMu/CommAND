package com.zthcpa.command.persistence.jpa;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionRepository;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

@Transactional
public class JpaDefinitionRepositoryAdapter implements DefinitionRepository {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public JpaDefinitionRepositoryAdapter(
            EntityManager entityManager,
            ObjectMapper mapper
    ) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    @Override
    public void saveIfAbsent(DefinitionDocument definition) {
        entityManager.createNativeQuery("""
                INSERT INTO command_runtime.command_definitions
                    (kind, id, definition_version, schema_version, status, document,
                     checksum, owner, created_at, updated_at)
                VALUES
                    (:kind, :id, :definitionVersion, :schemaVersion, :status,
                     CAST(:document AS jsonb), :checksum, :owner, :createdAt, :updatedAt)
                ON CONFLICT (kind, id, definition_version) DO NOTHING
                """)
                .setParameter("kind", definition.key().kind().value())
                .setParameter("id", definition.key().id())
                .setParameter("definitionVersion", definition.key().version())
                .setParameter("schemaVersion", definition.schemaVersion())
                .setParameter("status", definition.status().value())
                .setParameter("document", writeJson(definition.content()))
                .setParameter("checksum", definition.checksum())
                .setParameter("owner", "command")
                .setParameter("createdAt", Instant.now())
                .setParameter("updatedAt", Instant.now())
                .executeUpdate();
    }

    @Override
    public List<DefinitionDocument> list() {
        return entityManager.createQuery(
                        "select d from CommandDefinitionEntity d order by d.kind, d.id, d.definitionVersion",
                        com.zthcpa.command.persistence.entity.definition.CommandDefinitionEntity.class
                )
                .getResultList()
                .stream()
                .map(entity -> new DefinitionDocument(
                        new com.zthcpa.command.contract.DefinitionKey(
                                com.zthcpa.command.contract.DefinitionKind.fromValue(entity.getKind()),
                                entity.getId(),
                                entity.getDefinitionVersion()
                        ),
                        entity.getSchemaVersion(),
                        com.zthcpa.command.contract.DefinitionStatus.fromValue(entity.getStatus()),
                        entity.getDocument(),
                        entity.getChecksum(),
                        "jpa:command_runtime.command_definitions"
                ))
                .toList();
    }

    private String writeJson(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Cannot serialize command definition JSON", exception);
        }
    }
}
