package com.zthcpa.command.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionRegistry;
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
        var planner = new PipelineExecutionPlanner(registry);

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

        assertThrows(RunSubmissionException.class, () -> new PipelineExecutionPlanner(registry).plan(
                pipeline.key(), Map.of()
        ));
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
