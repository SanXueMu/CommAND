package com.zthcpa.command;

import com.zthcpa.command.api.RecoveryStatusPort;
import com.zthcpa.command.runtime.recovery.CleanRecoveryLoop;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "command.clean.scheduler.recovery-enabled=true",
        "command.clean.scheduler.recovery-poll-interval=1h"
})
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class RecoveryEnabledIntegrationTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private RecoveryStatusPort recoveryStatus;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void createsRecoveryLoopAndExposesEnabledStatus() {
        assertNotNull(context.getBean(CleanRecoveryLoop.class));
        assertTrue(recoveryStatus.status().enabled());
        assertTrue(recoveryStatus.status().active());
        assertEquals(0, recoveryStatus.status().errors());
    }
}
