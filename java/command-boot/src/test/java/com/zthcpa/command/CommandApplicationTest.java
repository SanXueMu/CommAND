package com.zthcpa.command;

import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.catalog.ToolCatalog;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class CommandApplicationTest {
    @Autowired
    private DefinitionRegistry definitionRegistry;

    @Autowired
    private ToolCatalog toolCatalog;

    @Autowired
    private ApplicationContext context;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void startsWithBuiltInWorkflowRegistry() {
        assertEquals(
                "ocr.extract-document",
                definitionRegistry.getActive(DefinitionKind.WORKFLOW, "ocr.extract-document").key().id()
        );
        assertTrue(context.getBeansOfType(com.zthcpa.command.runtime.scheduler.CleanSchedulerLoop.class)
                .containsKey("cleanSchedulerLoop"));
    }

    @Test
    void loadsToolCatalogSeparatelyFromDefinitionRegistry() {
        assertEquals(22, toolCatalog.list().size());
        assertEquals(0, definitionRegistry.list(DefinitionKind.TOOL).size());
    }

    @Test
    void exposesEnabledSchedulerStatus() throws Exception {
        mockMvc.perform(get("/api/system/scheduler"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true))
                .andExpect(jsonPath("$.active").value(true));
    }

    @Test
    void exposesDisabledRecoveryStatus() throws Exception {
        mockMvc.perform(get("/api/system/recovery"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false))
                .andExpect(jsonPath("$.active").value(false))
                .andExpect(jsonPath("$.polls").value(0))
                .andExpect(jsonPath("$.recovered").value(0))
                .andExpect(jsonPath("$.errors").value(0));
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }
}
