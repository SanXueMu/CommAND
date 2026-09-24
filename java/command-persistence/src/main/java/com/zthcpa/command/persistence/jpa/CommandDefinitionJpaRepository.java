package com.zthcpa.command.persistence.jpa;

import com.zthcpa.command.persistence.entity.definition.CommandDefinitionEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CommandDefinitionJpaRepository extends JpaRepository<
        CommandDefinitionEntity,
        com.zthcpa.command.persistence.entity.definition.CommandDefinitionId
> {
    Optional<CommandDefinitionEntity> findByKindAndIdAndStatus(String kind, String id, String status);

    List<CommandDefinitionEntity> findByKindAndStatusOrderByIdAscDefinitionVersionAsc(
            String kind, String status
    );
}
