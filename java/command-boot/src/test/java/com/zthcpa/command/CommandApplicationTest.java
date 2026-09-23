package com.zthcpa.command;

import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DisabledIfSystemProperty(named = "command.database.profile", matches = "true")
class CommandApplicationTest {
    @Autowired
    private DefinitionRegistry definitionRegistry;

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
        assertFalse(context.getBeansOfType(com.zthcpa.command.runtime.CleanSchedulerLoop.class)
                .containsKey("cleanSchedulerLoop"));
    }

    @Test
    void exposesDisabledSchedulerStatusWithoutDatabase() throws Exception {
        mockMvc.perform(get("/api/system/scheduler"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false))
                .andExpect(jsonPath("$.active").value(false))
                .andExpect(jsonPath("$.polls").value(0));
    }
}
