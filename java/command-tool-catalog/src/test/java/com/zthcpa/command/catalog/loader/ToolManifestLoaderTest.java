package com.zthcpa.command.catalog.loader;

import com.zthcpa.command.contract.RuntimeKind;
import com.zthcpa.command.contract.ToolKey;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ToolManifestLoaderTest {
    @Test
    void loadsBuiltInJavaToolCatalogWithoutInstantiatingImplementations() {
        var catalog = new ToolManifestLoader(
                getClass().getClassLoader(),
                new com.fasterxml.jackson.databind.ObjectMapper()
        ).load("tools/index.txt");

        var descriptor = catalog.get(new ToolKey("llm.chat.complete-json", 1));
        assertEquals(RuntimeKind.INPROC, descriptor.runtimeKind());
        assertEquals("com.zthcpa.command.tools.llm.LlmChatCompleteJsonTool", descriptor.manifest().get("entry"));
        assertEquals(20, catalog.list().size());
        assertTrue(descriptor.manifest().containsKey("output_schema"));
    }
}
