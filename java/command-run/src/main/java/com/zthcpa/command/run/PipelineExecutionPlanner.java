package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.workflow.CapabilityPipelineDefinition;
import com.zthcpa.command.workflow.DefinitionReference;
import com.zthcpa.command.workflow.WorkflowDefinitionReader;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class PipelineExecutionPlanner {
    private final DefinitionRegistry definitions;
    private final WorkflowDefinitionReader reader;

    public PipelineExecutionPlanner(DefinitionRegistry definitions) {
        this.definitions = Objects.requireNonNull(definitions, "definitions");
        this.reader = new WorkflowDefinitionReader();
    }

    public PipelineExecutionPlan plan(DefinitionKey pipelineKey, Map<String, Object> input) {
        if (pipelineKey.kind() != DefinitionKind.CAPABILITY_PIPELINE) {
            throw new RunSubmissionException("Expected capability pipeline: " + pipelineKey);
        }
        DefinitionDocument document = definitions.get(pipelineKey);
        CapabilityPipelineDefinition pipeline = reader.readPipeline(document);
        List<PipelineExecutionPlan.StepPlan> steps = new ArrayList<>();
        for (int index = 0; index < pipeline.steps().size(); index++) {
            CapabilityPipelineDefinition.PipelineStep step = pipeline.steps().get(index);
            DefinitionReference reference = step.reference();
            if (reference.tool() == null) {
                throw new RunSubmissionException(
                        "Composite pipeline step requires a separate subrun boundary: " + step.id()
                );
            }
            steps.add(new PipelineExecutionPlan.StepPlan(
                    index, step.id(),
                    new DefinitionKey(DefinitionKind.TOOL, reference.tool().id(), reference.tool().version()),
                    input,
                    1
            ));
        }
        return new PipelineExecutionPlan(pipelineKey, steps);
    }
}
