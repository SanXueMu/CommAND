package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionRepository;
import com.zthcpa.command.contract.RunDefinitionSnapshotRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Conditional;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import javax.sql.DataSource;

@Configuration
@Conditional(DataSourcePresentCondition.class)
public class JdbcPersistenceConfiguration {
    @Bean
    NamedParameterJdbcTemplate commandJdbcTemplate(DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    DefinitionRepository commandDefinitionRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        return new JdbcDefinitionRepository(jdbc, mapper);
    }

    @Bean
    RunDefinitionSnapshotRepository commandRunDefinitionSnapshotRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper
    ) {
        return new JdbcRunDefinitionSnapshotRepository(jdbc, mapper);
    }

    @Bean
    TaskRepository commandTaskRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        return new JdbcTaskRepository(jdbc, mapper);
    }
}
