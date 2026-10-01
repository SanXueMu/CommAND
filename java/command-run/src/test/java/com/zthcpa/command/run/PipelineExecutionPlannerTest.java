package com.zthcpa.command.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.RuntimeKind;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.catalog.InMemoryToolCatalog;
import com.zthcpa.command.definition.loader.JsonDefinitionParser;
import com.zthcpa.command.definition.registry.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.validation.DefinitionReferenceValidator;
import com.zthcpa.command.definition.validation.DefinitionSetValidator;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PipelineExecutionPlannerTest {
    @Test
    void plansToolStepsInDefinitionOrder() {
        DefinitionRegistry registry = registry();
        var planner = new PipelineExecutionPlanner(registry, tools());

        PipelineExecutionPlan plan = planner.plan(
                new com.zthcpa.command.contract.DefinitionKey(
                        com.zthcpa.command.contract.DefinitionKind.CAPABILITY_PIPELINE,
                        "ocr.extract-by-template", 1
                ),
                Map.of("file", "sample.pdf")
        );

        assertEquals(3, plan.steps().size());
        assertEquals("file.inspect", plan.steps().get(0).tool().id());
        assertEquals("ocr.page.extract", plan.steps().get(1).tool().id());
        assertEquals("ocr.result.persist", plan.steps().get(2).tool().id());
    }

    @Test
    void rejectsCompositeStepUntilSubrunBoundaryExists() {
        DefinitionDocument pipeline = parse(new JsonDefinitionParser(new ObjectMapper()), """
                {"kind":"capability_pipeline","id":"composite","version":1,
                 "title":"Composite pipeline",
                 "schema_version":1,"status":"active","steps":[
                   {"id":"nested","definition_ref":{"kind":"capability_pipeline","id":"nested","version":1}}
                 ]}
                """);
        DefinitionRegistry registry = new InMemoryDefinitionRegistry(
                List.of(pipeline, nestedPipeline()), new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );

        assertThrows(RunSubmissionException.class, () -> new PipelineExecutionPlanner(registry, tools()).plan(
                pipeline.key(), Map.of()
        ));
    }

    @Test
    void plansTextFileTranslationWithExplicitExtractedTextMapping() {
        var parser = new JsonDefinitionParser(new ObjectMapper());
        DefinitionDocument pipeline = parse(parser, """
                {"kind":"capability_pipeline","id":"translate.file-text","version":1,
                 "title":"Text file translation","schema_version":1,"status":"active","steps":[
                  {"id":"extract","definition_ref":{"kind":"tool","id":"txt.extract.text","version":1}},
                  {"id":"translate","definition_ref":{"kind":"tool","id":"text.translate","version":1},
                   "input":{"text":"$step.extract.units.0.text","target_lang":"$run.target_lang"}}
                 ]}
                """);
        DefinitionRegistry registry = new InMemoryDefinitionRegistry(
                List.of(pipeline), new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );
        PipelineExecutionPlan plan = new PipelineExecutionPlanner(registry, new InMemoryToolCatalog(List.of(
                tool("txt.extract.text"), tool("text.translate")
        ))).plan(pipeline.key(), Map.of("file", "input.txt", "target_lang", "English"));

        assertEquals(List.of("txt.extract.text", "text.translate"), plan.steps().stream().map(step -> step.tool().id()).toList());
        assertEquals("$step.extract.units.0.text", plan.steps().get(1).inputTemplate().get("text"));
    }

    private DefinitionRegistry registry() {
        var parser = new JsonDefinitionParser(new ObjectMapper());
        DefinitionDocument workflow = parse(parser, """
                {"kind":"workflow","id":"test.workflow","version":1,
                 "schema_version":1,"status":"active","capability_pipeline_ref":
                 {"kind":"capability_pipeline","id":"ocr.extract-by-template","version":1}}
                """);
        DefinitionDocument pipeline = parse(parser, """
                {"kind":"capability_pipeline","id":"ocr.extract-by-template","version":1,
                 "title":"OCR extraction",
                 "schema_version":1,"status":"active","steps":[
                   {"id":"inspect","definition_ref":{"kind":"tool","id":"file.inspect","version":1}},
                   {"id":"extract","definition_ref":{"kind":"tool","id":"ocr.page.extract","version":1}},
                   {"id":"persist","definition_ref":{"kind":"tool","id":"ocr.result.persist","version":1}}
                 ]}
                """);
        return new InMemoryDefinitionRegistry(
                List.of(workflow, pipeline), new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );
    }

    private InMemoryToolCatalog tools() {
        return new InMemoryToolCatalog(List.of(
                tool("file.inspect"),
                tool("ocr.page.extract"),
                tool("ocr.result.persist"),
                tool("nested.tool")
        ));
    }

    private ToolDescriptor tool(String id) {
        return new ToolDescriptor(new ToolKey(id, 1), RuntimeKind.INPROC, "active", Map.of());
    }

    private DefinitionDocument nestedPipeline() {
        return parse(new JsonDefinitionParser(new ObjectMapper()), """
                {"kind":"capability_pipeline","id":"nested","version":1,
                 "title":"Nested pipeline","schema_version":1,"status":"active",
                 "steps":[{"id":"nested-tool","definition_ref":{"kind":"tool","id":"nested.tool","version":1}}]}
                """);
    }

    private DefinitionDocument parse(JsonDefinitionParser parser, String json) {
        return parser.parse(
                new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8)),
                "test-definition.json"
        );
    }
}
