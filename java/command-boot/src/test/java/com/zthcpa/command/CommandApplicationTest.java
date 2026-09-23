package com.zthcpa.command;

import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.DisabledIfSystemProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@DisabledIfSystemProperty(named = "command.database.profile", matches = "true")
class CommandApplicationTest {
    @Autowired
    private DefinitionRegistry definitionRegistry;

    @Test
    void startsWithBuiltInWorkflowRegistry() {
        assertEquals(
                "ocr.extract-document",
                definitionRegistry.getActive(DefinitionKind.WORKFLOW, "ocr.extract-document").key().id()
        );
    }
}
