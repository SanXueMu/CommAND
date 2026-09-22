package com.zthcpa.command.definition;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionKind;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClasspathDefinitionLoaderTest {
    @Test
    void loadsBuiltInWorkflowFromResourceIndex() {
        ClasspathDefinitionLoader loader = new ClasspathDefinitionLoader(
                getClass().getClassLoader(),
                "definitions/index.txt",
                new JsonDefinitionParser(new ObjectMapper())
        );

        var definitions = loader.load();

        assertEquals(2, definitions.size());
        var workflow = definitions.stream()
                .filter(definition -> definition.key().kind() == DefinitionKind.WORKFLOW)
                .findFirst()
                .orElseThrow();
        assertEquals("ocr.extract-document", workflow.key().id());
    }
}
