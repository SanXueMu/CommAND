package com.zthcpa.command.persistence.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.artifact.CleanArtifactRepository;
import com.zthcpa.command.persistence.artifact.HibernateCleanArtifactRepository;
import com.zthcpa.command.persistence.event.CleanEventRepository;
import com.zthcpa.command.persistence.event.HibernateCleanEventRepository;
import com.zthcpa.command.persistence.run.CleanRecoveryRepository;
import com.zthcpa.command.persistence.run.CleanRunQueryRepository;
import com.zthcpa.command.persistence.run.CleanRunSubmissionRepository;
import com.zthcpa.command.persistence.run.CleanStepCoordinatorRepository;
import com.zthcpa.command.persistence.task.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.task.CleanTaskRepository;
import com.zthcpa.command.persistence.task.HibernateCleanTaskRepository;
import com.zthcpa.command.contract.LlmConfigurationPort;
import jakarta.persistence.EntityManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;


@Configuration
public class HibernatePersistenceConfiguration {

    @Bean
    CleanTaskRepository cleanTaskRepository(EntityManager entityManager, ObjectMapper mapper) {
        return new HibernateCleanTaskRepository(entityManager, mapper);
    }

    @Bean
    CleanEventRepository cleanEventRepository(EntityManager entityManager) {
        return new HibernateCleanEventRepository(entityManager);
    }

    @Bean
    CleanRunCompletionRepository cleanRunCompletionRepository(
            EntityManager entityManager, ObjectMapper mapper
    ) {
        return new CleanRunCompletionRepository(entityManager, mapper);
    }

    @Bean
    CleanStepCoordinatorRepository cleanStepCoordinatorRepository(
            EntityManager entityManager, ObjectMapper mapper
    ) {
        return new CleanStepCoordinatorRepository(entityManager, mapper);
    }

    @Bean
    CleanRecoveryRepository cleanRecoveryRepository(
            EntityManager entityManager, ObjectMapper mapper
    ) {
        return new CleanRecoveryRepository(entityManager, mapper);
    }

    @Bean
    CleanRunQueryRepository cleanRunQueryRepository(EntityManager entityManager) {
        return new CleanRunQueryRepository(entityManager);
    }

    @Bean
    CleanArtifactRepository cleanArtifactRepository(EntityManager entityManager) {
        return new HibernateCleanArtifactRepository(entityManager);
    }

    @Bean
    CleanRunSubmissionRepository cleanRunSubmissionRepository(EntityManager entityManager) {
        return new CleanRunSubmissionRepository(entityManager);
    }

    @Bean
    LlmConfigurationPort llmConfigurationPort(EntityManager entityManager) {
        return new HibernateLlmConfigurationService(entityManager);
    }

}
