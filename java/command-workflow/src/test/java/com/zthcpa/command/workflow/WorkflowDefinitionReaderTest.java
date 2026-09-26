package com.zthcpa.command.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.definition.loader.JsonDefinitionParser;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class WorkflowDefinitionReaderTest {
    private final JsonDefinitionParser parser = new JsonDefinitionParser(new ObjectMapper());
    private final WorkflowDefinitionReader reader = new WorkflowDefinitionReader();

    @Test
    void readsWorkflowWithoutExposingRawStepDetails() {
        WorkflowDefinition workflow = reader.readWorkflow(parse("""
                {"schema_version":1,"kind":"workflow","id":"ocr.extract-document",
                 "version":1,"status":"active","title":"Extract",
                 "capability_pipeline_ref":{"kind":"capability_pipeline","id":"ocr.extract-by-template","version":1},
                 "input_schema":{"type":"object"},"output":{"result_kind":"ocr_result_dataset"}}
                """));

        assertEquals("ocr.extract-document", workflow.key().id());
        assertEquals("ocr.extract-by-template", workflow.capabilityPipeline().id());
    }

    @Test
    void readsPipelineToolAndDefinitionReferences() {
        CapabilityPipelineDefinition pipeline = reader.readPipeline(parse("""
                {"schema_version":1,"kind":"capability_pipeline","id":"ocr.extract-by-template",
                 "version":1,"status":"active","title":"Extract",
                 "steps":[
                   {"id":"inspect","definition_ref":{"kind":"tool","id":"file.inspect","version":1}},
                   {"id":"nested","definition_ref":{"kind":"capability_pipeline","id":"ocr.other","version":1}}
                 ]}
                """));

        assertEquals(2, pipeline.steps().size());
        assertInstanceOf(com.zthcpa.command.contract.ToolKey.class, pipeline.steps().get(0).reference().tool());
        assertEquals("ocr.other", pipeline.steps().get(1).reference().definition().id());
    }

    private DefinitionDocument parse(String json) {
        return parser.parse(
                new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8)),
                "test.json"
        );
    }
}
