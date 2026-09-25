package com.zthcpa.command;

import com.zthcpa.command.runtime.tool.InProcessToolRuntime;
import com.zthcpa.command.runtime.tool.ToolRuntimeRouter;
import com.zthcpa.command.runtime.worker.HttpWorkerRuntime;
import com.zthcpa.command.runtime.worker.WorkerHealthChecker;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "command.clean.scheduler.enabled=true",
        "command.clean.scheduler.worker-id=java-only-test",
        "command.clean.scheduler.poll-interval=50ms"
})
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class JavaOnlySchedulerIntegrationTest {
    @Autowired
    private ApplicationContext context;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void startsSchedulerWithInProcessRuntimeAndNoExternalWorker() {
        assertNotNull(context.getBean(InProcessToolRuntime.class));
        assertNotNull(context.getBean(ToolRuntimeRouter.class));
        assertTrue(context.getBeansOfType(HttpWorkerRuntime.class).isEmpty());
        assertTrue(context.getBeansOfType(WorkerHealthChecker.class).isEmpty());
    }
}
