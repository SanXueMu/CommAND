package com.zthcpa.command;

import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
@DisabledIfSystemProperty(named = "command.database.profile", matches = "true")
class CommandApplicationTest {
    @Autowired
    private DefinitionRegistry definitionRegistry;

    @Autowired
    private ApplicationContext context;

    @Test
    void startsWithBuiltInWorkflowRegistry() {
        assertEquals(
                "ocr.extract-document",
                definitionRegistry.getActive(DefinitionKind.WORKFLOW, "ocr.extract-document").key().id()
        );
        assertFalse(context.getBeansOfType(com.zthcpa.command.runtime.CleanSchedulerLoop.class)
                .containsKey("cleanSchedulerLoop"));
    }
}
