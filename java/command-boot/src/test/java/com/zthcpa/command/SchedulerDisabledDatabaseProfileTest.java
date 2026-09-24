package com.zthcpa.command;

import com.zthcpa.command.runtime.CleanSchedulerLoop;
import com.zthcpa.command.runtime.CleanRecoveryPoller;
import com.zthcpa.command.runtime.CleanRecoveryLoop;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
@ActiveProfiles("database")
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class SchedulerDisabledDatabaseProfileTest {
    @Autowired
    private ApplicationContext context;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void doesNotCreateSchedulerWhenDisabled() {
        assertFalse(context.getBeansOfType(CleanSchedulerLoop.class).containsKey("cleanSchedulerLoop"));
        assertFalse(context.getBeansOfType(CleanRecoveryPoller.class).containsKey("cleanRecoveryPoller"));
        assertFalse(context.getBeansOfType(CleanRecoveryLoop.class).containsKey("cleanRecoveryLoop"));
    }
}
