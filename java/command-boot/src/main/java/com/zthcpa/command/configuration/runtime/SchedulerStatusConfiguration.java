package com.zthcpa.command.configuration.runtime;

import com.zthcpa.command.api.port.SchedulerStatusPort;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SchedulerStatusConfiguration {
    @Bean
    @ConditionalOnMissingBean(SchedulerStatusPort.class)
    SchedulerStatusPort disabledSchedulerStatus() {
        return () -> new SchedulerStatusPort.Status(
                false, false, 0, 0, 0, 0, null, null
        );
    }
}
