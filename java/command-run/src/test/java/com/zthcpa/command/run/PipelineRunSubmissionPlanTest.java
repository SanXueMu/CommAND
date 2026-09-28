package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PipelineRunSubmissionPlanTest {
    @Test
    void bindsTaskIdsToEveryPlannedStep() {
        DefinitionKey pipeline = new DefinitionKey(DefinitionKind.CAPABILITY_PIPELINE, "pipeline", 1);
        DefinitionDocument document = new DefinitionDocument(
                pipeline, 1, com.zthcpa.command.contract.DefinitionStatus.ACTIVE,
                Map.of("title", "pipeline"), "0".repeat(64), "test"
        );
        var execution = new PipelineExecutionPlan(pipeline, List.of(
                new PipelineExecutionPlan.StepPlan(0, "one", new DefinitionKey(DefinitionKind.TOOL, "one", 1), Map.of(), 1),
                new PipelineExecutionPlan.StepPlan(1, "two", new DefinitionKey(DefinitionKind.TOOL, "two", 1), Map.of(), 1)
        ));
        var plan = new PipelineRunSubmissionPlan(
                "run-1", new DefinitionKey(DefinitionKind.WORKFLOW, "workflow", 1),
                Map.of(), List.of(document), execution, List.of(
                        PipelineExecutionIdentifiers.taskId("run-1", 0),
                        PipelineExecutionIdentifiers.taskId("run-1", 1)
                )
        );

        assertEquals(PipelineExecutionIdentifiers.taskId("run-1", 0), plan.firstTaskId());
        assertEquals(2, plan.taskIds().size());
    }
}
