package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.jpa.CommandDefinitionJpaRepository;
import com.zthcpa.command.persistence.jpa.JpaDefinitionQueryAdapter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@Profile("database")
@EnableJpaRepositories(basePackageClasses = CommandDefinitionJpaRepository.class)
public class JpaDefinitionConfiguration {
    @Bean
    DefinitionQueryPort definitionQueryPort(
            CommandDefinitionJpaRepository repository,
            ObjectMapper mapper
    ) {
        return new JpaDefinitionQueryAdapter(repository, mapper);
    }
}
