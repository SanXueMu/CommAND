package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
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

}
