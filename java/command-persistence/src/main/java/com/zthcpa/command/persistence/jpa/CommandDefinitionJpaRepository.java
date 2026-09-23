package com.zthcpa.command.persistence.jpa;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CommandDefinitionJpaRepository extends JpaRepository<CommandDefinitionEntity, CommandDefinitionId> {
    Optional<CommandDefinitionEntity> findByKindAndIdAndStatus(String kind, String id, String status);

    List<CommandDefinitionEntity> findByKindAndStatusOrderByIdAscDefinitionVersionAsc(
            String kind, String status
    );
}
