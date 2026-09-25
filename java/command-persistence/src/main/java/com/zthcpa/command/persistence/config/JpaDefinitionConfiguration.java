package com.zthcpa.command.persistence.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionRepository;
import com.zthcpa.command.contract.RunDefinitionSnapshotRepository;
import com.zthcpa.command.persistence.definition.CommandDefinitionJpaRepository;
import com.zthcpa.command.persistence.definition.DefinitionQueryPort;
import com.zthcpa.command.persistence.definition.JpaDefinitionRepositoryAdapter;
import com.zthcpa.command.persistence.definition.JpaDefinitionQueryAdapter;
import com.zthcpa.command.persistence.definition.JpaRunDefinitionSnapshotRepositoryAdapter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import jakarta.persistence.EntityManager;

@Configuration
@EnableJpaRepositories(basePackageClasses = CommandDefinitionJpaRepository.class)
public class JpaDefinitionConfiguration {
    @Bean
    DefinitionQueryPort definitionQueryPort(
            CommandDefinitionJpaRepository repository,
            ObjectMapper mapper
    ) {
        return new JpaDefinitionQueryAdapter(repository, mapper);
    }

    @Bean
    DefinitionRepository commandDefinitionRepository(EntityManager entityManager, ObjectMapper mapper) {
        return new JpaDefinitionRepositoryAdapter(entityManager, mapper);
    }

    @Bean
    RunDefinitionSnapshotRepository commandRunDefinitionSnapshotRepository(EntityManager entityManager) {
        return new JpaRunDefinitionSnapshotRepositoryAdapter(entityManager);
    }
}
