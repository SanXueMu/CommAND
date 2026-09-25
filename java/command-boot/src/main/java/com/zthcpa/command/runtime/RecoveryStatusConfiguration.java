package com.zthcpa.command.runtime;

import com.zthcpa.command.api.RecoveryStatusPort;
import com.zthcpa.command.runtime.recovery.CleanRecoveryLoop;
import com.zthcpa.command.runtime.recovery.RecoveryMetrics;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RecoveryStatusConfiguration {
    @Bean
    @ConditionalOnProperty(
            prefix = "command.clean.scheduler",
            name = "recovery-enabled",
            havingValue = "true"
    )
    RecoveryStatusPort enabledRecoveryStatus(CleanRecoveryLoop loop) {
        return () -> {
            RecoveryMetrics.Snapshot snapshot = loop.metrics();
            RecoveryMetrics.ErrorSnapshot error = snapshot.lastError();
            return new RecoveryStatusPort.Status(
                    true,
                    snapshot.active(),
                    snapshot.polls(),
                    snapshot.recovered(),
                    snapshot.errors(),
                    snapshot.lastPollAt(),
                    snapshot.lastRecovered(),
                    error == null ? null : new RecoveryStatusPort.ErrorStatus(error.type(), error.message())
            );
        };
    }

    @Bean
    @ConditionalOnMissingBean(RecoveryStatusPort.class)
    RecoveryStatusPort disabledRecoveryStatus() {
        return () -> new RecoveryStatusPort.Status(
                false, false, 0, 0, 0, null, null, null
        );
    }
}
