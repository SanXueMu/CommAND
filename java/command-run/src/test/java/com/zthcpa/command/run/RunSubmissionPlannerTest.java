package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionStatus;
import com.zthcpa.command.definition.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.DefinitionSetValidator;
import com.zthcpa.command.definition.DefinitionReferenceValidator;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RunSubmissionPlannerTest {
    private static final String CHECKSUM_A = "3e39a652e63fe7c7617ec4c28c310610c15f470d4ef6d09d4a1ea675f9e1ee1c";
    private static final String CHECKSUM_B = "c26760a42cc693b36c3eff9653225d29e0376c3f0eed8ce80baef5e5dcef4618";

    @Test
    void createsRunAndFirstToolTaskPlanWithDefinitionSnapshots() {
        DefinitionDocument pipeline = pipeline();
        DefinitionDocument workflow = workflow();
        var registry = new InMemoryDefinitionRegistry(
                List.of(workflow, pipeline), new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );
        AtomicInteger ids = new AtomicInteger();

        RunSubmissionPlan plan = new RunSubmissionPlanner(registry, () -> "id-" + ids.incrementAndGet())
                .plan("ocr.extract-document", Map.of("file", "a.pdf", "template_id", "invoice"));

        assertEquals("id-1", plan.runId());
        assertEquals("id-2", plan.firstTask().handle());
        assertEquals("file.inspect", plan.firstTask().tool().id());
        assertEquals(2, plan.definitions().size());
        assertEquals("a.pdf", plan.firstTask().input().get("file"));
    }

    @Test
    void rejectsSubrunAsFirstStepUntilSubrunSubmissionExists() {
        DefinitionDocument subrunPipeline = new DefinitionDocument(
                new DefinitionKey(DefinitionKind.CAPABILITY_PIPELINE, "subrun", 1), 1,
                DefinitionStatus.ACTIVE, Map.of(
                        "kind", "capability_pipeline", "id", "subrun", "version", 1,
                        "steps", List.of(Map.of("definition_ref", Map.of(
                                "kind", "capability_pipeline", "id", "nested", "version", 1
                        )))
                ), CHECKSUM_A, "test"
        );
        DefinitionDocument workflow = new DefinitionDocument(
                new DefinitionKey(DefinitionKind.WORKFLOW, "subrun-workflow", 1), 1,
                DefinitionStatus.ACTIVE, Map.of(
                        "kind", "workflow", "id", "subrun-workflow", "version", 1,
                        "capability_pipeline_ref", Map.of(
                                "kind", "capability_pipeline", "id", "subrun", "version", 1
                        )
                ), CHECKSUM_B, "test"
        );
        DefinitionDocument nested = new DefinitionDocument(
                new DefinitionKey(DefinitionKind.CAPABILITY_PIPELINE, "nested", 1), 1,
                DefinitionStatus.ACTIVE, Map.of(
                        "kind", "capability_pipeline", "id", "nested", "version", 1,
                        "steps", List.of(Map.of("definition_ref", Map.of(
                                "kind", "tool", "id", "file.inspect", "version", 1
                        )))
                ), CHECKSUM_A, "test"
        );
        var registry = new InMemoryDefinitionRegistry(
                List.of(workflow, subrunPipeline, nested),
                new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );

        assertThrows(RunSubmissionException.class, () -> new RunSubmissionPlanner(registry, () -> "id")
                .plan("subrun-workflow", Map.of()));
    }

    private DefinitionDocument workflow() {
        return new DefinitionDocument(
                new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", 1), 1,
                DefinitionStatus.ACTIVE, Map.of(
                        "kind", "workflow", "id", "ocr.extract-document", "version", 1,
                        "capability_pipeline_ref", Map.of(
                                "kind", "capability_pipeline", "id", "ocr.extract-by-template", "version", 1
                        )
                ), CHECKSUM_B, "test"
        );
    }

    private DefinitionDocument pipeline() {
        return new DefinitionDocument(
                new DefinitionKey(DefinitionKind.CAPABILITY_PIPELINE, "ocr.extract-by-template", 1), 1,
                DefinitionStatus.ACTIVE, Map.of(
                        "kind", "capability_pipeline", "id", "ocr.extract-by-template", "version", 1,
                        "steps", List.of(Map.of(
                                "id", "inspect", "definition_ref", Map.of(
                                        "kind", "tool", "id", "file.inspect", "version", 1
                                )
                        ))
                ), CHECKSUM_A, "test"
        );
    }
}
