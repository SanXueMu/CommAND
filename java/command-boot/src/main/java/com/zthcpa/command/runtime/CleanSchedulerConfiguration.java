package com.zthcpa.command.runtime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.CleanEventRepository;
import com.zthcpa.command.persistence.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.CleanTaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import javax.sql.DataSource;
import java.net.URI;
import java.time.Duration;

@Configuration
@Profile("database")
@EnableConfigurationProperties(CleanSchedulerProperties.class)
public class CleanSchedulerConfiguration {
    private static final Logger log = LoggerFactory.getLogger(CleanSchedulerConfiguration.class);

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    HttpWorkerRuntime cleanWorkerRuntime(CleanSchedulerProperties properties, ObjectMapper mapper) {
        return new HttpWorkerRuntime(
                requireUri(properties.getWorkerBaseUrl()),
                mapper,
                requirePositive(properties.getWorkerTimeout(), "workerTimeout")
        );
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    JdbcTaskExecutionPort cleanTaskExecutionPort(
            CleanTaskRepository tasks,
            CleanEventRepository events,
            CleanRunCompletionRepository completion
    ) {
        return new JdbcTaskExecutionPort(tasks, events, completion);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    TaskDispatcher cleanTaskDispatcher(JdbcTaskExecutionPort tasks, HttpWorkerRuntime worker) {
        return new TaskDispatcher(tasks, worker);
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    CleanSchedulerLoop cleanSchedulerLoop(
            TaskDispatcher dispatcher,
            CleanSchedulerProperties properties
    ) {
        String workerId = requireText(properties.getWorkerId(), "workerId");
        CleanScheduler scheduler = new CleanScheduler(dispatcher);
        CleanSchedulerLoop loop = new CleanSchedulerLoop(
                scheduler,
                workerId,
                requirePositive(properties.getPollInterval(), "pollInterval"),
                exception -> log.error("Clean scheduler poll failed", exception)
        );
        loop.start();
        return loop;
    }

    private static URI requireUri(String value) {
        String text = requireText(value, "workerBaseUrl");
        try {
            URI uri = URI.create(text);
            if (uri.getScheme() == null || uri.getHost() == null) {
                throw new IllegalArgumentException("workerBaseUrl must be an absolute URI");
            }
            return uri;
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("workerBaseUrl is invalid", exception);
        }
    }

    private static Duration requirePositive(Duration value, String name) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(name + " must be positive");
        }
        return value;
    }

    private static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }
}
