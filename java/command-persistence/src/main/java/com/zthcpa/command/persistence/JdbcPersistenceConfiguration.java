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
    CleanTaskRepository cleanTaskRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        return new JdbcCleanTaskRepository(jdbc, mapper);
    }

    @Bean
    CleanEventRepository cleanEventRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        return new JdbcCleanEventRepository(jdbc, mapper);
    }

    @Bean
    CleanRunCompletionRepository cleanRunCompletionRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        return new CleanRunCompletionRepository(jdbc, mapper, dataSource);
    }

    @Bean
    CleanStepCoordinatorRepository cleanStepCoordinatorRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        return new CleanStepCoordinatorRepository(jdbc, mapper, dataSource);
    }

    @Bean
    CleanRecoveryRepository cleanRecoveryRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        return new CleanRecoveryRepository(jdbc, mapper, dataSource);
    }

    @Bean
    CleanRunSubmissionRepository cleanRunSubmissionRepository(
            NamedParameterJdbcTemplate jdbc,
            ObjectMapper mapper,
            DataSource dataSource
    ) {
        return new CleanRunSubmissionRepository(jdbc, mapper, dataSource);
    }

    @Bean
    TaskRepository commandTaskRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        return new JdbcTaskRepository(jdbc, mapper);
    }
}
