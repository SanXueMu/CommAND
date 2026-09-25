package com.zthcpa.command.persistence.definition;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;

import java.util.List;
import java.util.Optional;

public final class JpaDefinitionQueryAdapter implements DefinitionQueryPort {
    private final CommandDefinitionJpaRepository repository;
    private final ObjectMapper mapper;

    public JpaDefinitionQueryAdapter(CommandDefinitionJpaRepository repository, ObjectMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Optional<DefinitionDocument> findActive(String kind, String id) {
        return repository.findByKindAndIdAndStatus(kind, id, "active").map(this::toDocument);
    }

    @Override
    public List<DefinitionDocument> listActive(String kind) {
        return repository.findByKindAndStatusOrderByIdAscDefinitionVersionAsc(kind, "active")
                .stream()
                .map(this::toDocument)
                .toList();
    }

    private DefinitionDocument toDocument(CommandDefinitionEntity entity) {
        try {
            return new DefinitionDocument(
                    new DefinitionKey(
                            DefinitionKind.fromValue(entity.getKind()),
                            entity.getId(),
                            entity.getDefinitionVersion()
                    ),
                    entity.getSchemaVersion(),
                    DefinitionStatus.fromValue(entity.getStatus()),
                    entity.getDocument(),
                    entity.getChecksum(),
                    "jpa:command_runtime.command_definitions"
            );
        } catch (Exception exception) {
            throw new IllegalStateException(
                    "Invalid command definition JSON for " + entity.getKind() + "/" + entity.getId(), exception
            );
        }
    }
}
