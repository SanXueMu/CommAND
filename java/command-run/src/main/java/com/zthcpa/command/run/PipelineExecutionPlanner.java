package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.workflow.CapabilityPipelineDefinition;
import com.zthcpa.command.workflow.DefinitionReference;
import com.zthcpa.command.workflow.WorkflowDefinitionReader;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class PipelineExecutionPlanner {
    private final DefinitionRegistry definitions;
    private final ToolCatalog tools;
    private final WorkflowDefinitionReader reader;

    public PipelineExecutionPlanner(DefinitionRegistry definitions, ToolCatalog tools) {
        this.definitions = Objects.requireNonNull(definitions, "definitions");
        this.tools = Objects.requireNonNull(tools, "tools");
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
            DefinitionKey toolKey = new DefinitionKey(
                    DefinitionKind.TOOL, reference.tool().id(), reference.tool().version()
            );
            ToolDescriptor descriptor;
            try {
                descriptor = tools.get(new com.zthcpa.command.contract.ToolKey(
                        toolKey.id(), toolKey.version()
                ));
            } catch (RuntimeException exception) {
                throw new RunSubmissionException("Tool is not registered: " + toolKey);
            }
            if (!"active".equalsIgnoreCase(descriptor.status())) {
                throw new RunSubmissionException("Tool is not active: " + toolKey);
            }
            steps.add(new PipelineExecutionPlan.StepPlan(
                     index, step.id(),
                    toolKey,
                    index == 0 ? InputTemplateResolver.resolve(step.inputTemplate(), input, Map.of()) : input,
                    step.inputTemplate(),
                    1
            ));
        }
        return new PipelineExecutionPlan(pipelineKey, steps);
    }
}
