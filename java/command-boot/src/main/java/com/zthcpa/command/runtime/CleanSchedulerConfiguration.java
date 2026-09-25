package com.zthcpa.command.runtime;

import com.zthcpa.command.api.SchedulerStatusPort;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.event.CleanEventRepository;
import com.zthcpa.command.persistence.run.CleanRecoveryRepository;
import com.zthcpa.command.persistence.task.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.task.CleanTaskRepository;
import com.zthcpa.command.tools.spi.JavaToolRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.SmartLifecycle;

import java.net.URI;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;

@Configuration
@EnableConfigurationProperties(CleanSchedulerProperties.class)
public class CleanSchedulerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "recovery-enabled",
            havingValue = "true"
    )
    CleanRecoveryPoller cleanRecoveryPoller(
            CleanRecoveryRepository recovery,
            CleanSchedulerProperties properties
    ) {
        return new CleanRecoveryPoller(
                recovery::recoverStaleTasks,
                Clock.systemUTC(),
                requirePositive(properties.getStaleAfter(), "staleAfter"),
                requireBatchSize(properties.getRecoveryBatchSize())
        );
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "recovery-enabled",
            havingValue = "true"
    )
    CleanRecoveryLoop cleanRecoveryLoop(
            CleanRecoveryPoller poller,
            CleanSchedulerProperties properties
    ) {
        CleanRecoveryLoop loop = new CleanRecoveryLoop(
                poller,
                requirePositive(properties.getRecoveryPollInterval(), "recoveryPollInterval"),
                exception -> log.error("Clean recovery poll failed", exception)
        );
        return loop;
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "recovery-enabled",
            havingValue = "true"
    )
    SmartLifecycle cleanRecoveryLifecycle(CleanRecoveryLoop loop) {
        return new SmartLifecycle() {
            @Override
            public void start() {
                loop.start();
            }

            @Override
            public void stop() {
                loop.stop();
            }

            @Override
            public boolean isRunning() {
                return loop.isRunning();
            }
        };
    }

    private static final Logger log = LoggerFactory.getLogger(CleanSchedulerConfiguration.class);

    @Bean
    @ConditionalOnProperty(prefix = "command.clean.scheduler", name = "worker-base-url")
    HttpWorkerRuntime cleanWorkerRuntime(CleanSchedulerProperties properties, ObjectMapper mapper) {
        return new HttpWorkerRuntime(
                requireUri(properties.getWorkerBaseUrl()),
                mapper,
                requirePositive(properties.getWorkerTimeout(), "workerTimeout")
        );
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    InProcessToolRuntime cleanInProcessToolRuntime(JavaToolRegistry tools) {
        return new InProcessToolRuntime(tools);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    ToolRuntimeRouter cleanToolRuntimeRouter(
            JavaToolRegistry tools,
            InProcessToolRuntime inProcess,
            Optional<HttpWorkerRuntime> external
    ) {
        return new ToolRuntimeRouter(tools, inProcess, external.orElse(null));
    }

    @Bean
    @ConditionalOnProperty(prefix = "command.clean.scheduler", name = "worker-base-url")
    WorkerHealthChecker cleanWorkerHealthChecker(CleanSchedulerProperties properties) {
        return new WorkerHealthChecker(
                requireUri(properties.getWorkerBaseUrl()),
                requirePositive(properties.getWorkerTimeout(), "workerTimeout")
        );
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    PersistentTaskExecutionPort cleanTaskExecutionPort(
            CleanTaskRepository tasks,
            CleanEventRepository events,
            CleanRunCompletionRepository completion
    ) {
        return new PersistentTaskExecutionPort(tasks, events, completion);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    TaskDispatcher cleanTaskDispatcher(
            PersistentTaskExecutionPort tasks,
            ToolRuntimeRouter worker,
            CleanSchedulerProperties properties
    ) {
        return new TaskDispatcher(
                tasks,
                worker,
                requirePositive(properties.getJobPollInterval(), "jobPollInterval"),
                requirePositive(properties.getJobTimeout(), "jobTimeout"),
                requirePositive(properties.getHeartbeatInterval(), "heartbeatInterval")
        );
    }

    @Bean(destroyMethod = "")
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    CleanSchedulerLoop cleanSchedulerLoop(
            TaskDispatcher dispatcher,
            CleanSchedulerProperties properties,
            SchedulerMetrics metrics
    ) {
        String workerId = requireText(properties.getWorkerId(), "workerId");
        CleanScheduler scheduler = new CleanScheduler(dispatcher);
        return new CleanSchedulerLoop(
                scheduler,
                workerId,
                requirePositive(properties.getPollInterval(), "pollInterval"),
                exception -> log.error("Clean scheduler poll failed", exception),
                metrics
        );
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    SchedulerMetrics cleanSchedulerMetrics() {
        return new SchedulerMetrics();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    SchedulerStatusPort schedulerStatus(SchedulerMetrics metrics, SchedulerActivation activation) {
        return () -> toStatus(metrics.snapshot(activation.isActive()));
    }

    private static SchedulerStatusPort.Status toStatus(SchedulerMetrics.Snapshot snapshot) {
        SchedulerMetrics.ErrorSnapshot error = snapshot.lastError();
        return new SchedulerStatusPort.Status(
                true,
                snapshot.active(),
                snapshot.polls(),
                snapshot.dispatched(),
                snapshot.idle(),
                snapshot.errors(),
                snapshot.lastPollAt(),
                error == null ? null : new SchedulerStatusPort.ErrorStatus(error.type(), error.message())
        );
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "enabled",
            havingValue = "true"
    )
    SchedulerActivation schedulerActivation(
            Optional<WorkerHealthChecker> healthChecker,
            CleanSchedulerLoop loop
    ) {
        SchedulerActivation activation = new SchedulerActivation(
                () -> healthChecker.ifPresent(WorkerHealthChecker::verify),
                loop
        );
        activation.activate();
        return activation;
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

    private static int requireBatchSize(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("recoveryBatchSize must be between 1 and 1000");
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
