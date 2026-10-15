package com.zthcpa.command.api.application;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.DefinitionRepository;
import com.zthcpa.command.contract.DefinitionStatus;
import com.zthcpa.command.contract.RuntimeKind;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.run.RunSubmissionException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class CustomWorkflowApplicationService {
    private final DefinitionRepository definitions;
    private final DefinitionRegistry registry;
    private final ToolCatalog tools;
    private final ObjectMapper mapper;

    public CustomWorkflowApplicationService(DefinitionRepository definitions,
                                            DefinitionRegistry registry,
                                            ToolCatalog tools,
                                            ObjectMapper mapper) {
        this.definitions = definitions;
        this.registry = registry;
        this.tools = tools;
        this.mapper = mapper;
    }

    @Transactional
    public CustomWorkflowResponse create(CustomWorkflowRequest request) {
        if (request == null || request.name() == null || request.name().isBlank()) {
            throw new RunSubmissionException("Workflow name must not be blank");
        }
        if (request.steps() == null || request.steps().isEmpty() || request.steps().size() > 50) {
            throw new RunSubmissionException("Workflow must contain between 1 and 50 steps");
        }
        String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        String baseId = "custom." + slug(request.name());
        String pipelineId = baseId + ".pipeline." + suffix;
        String workflowId = baseId + ".workflow." + suffix;
        List<Map<String, Object>> pipelineSteps = new ArrayList<>();
        for (int index = 0; index < request.steps().size(); index++) {
            CustomStep step = request.steps().get(index);
            if (step == null || step.toolId() == null || step.toolId().isBlank()) {
                throw new RunSubmissionException("Tool step must contain toolId");
            }
            ToolDescriptor descriptor;
            try {
                descriptor = tools.get(new ToolKey(step.toolId(), step.toolVersion() == null ? 1 : step.toolVersion()));
            } catch (RuntimeException exception) {
                throw new RunSubmissionException("Tool is not registered: " + step.toolId());
            }
            if (!"active".equalsIgnoreCase(descriptor.status()) || descriptor.runtimeKind() != RuntimeKind.INPROC) {
                throw new RunSubmissionException("Only active INPROC tools can be composed: " + step.toolId());
            }
            Map<String, Object> reference = Map.of(
                    "kind", "tool", "id", descriptor.key().id(), "version", descriptor.key().version()
            );
            Map<String, Object> pipelineStep = new LinkedHashMap<>();
            pipelineStep.put("id", step.id() == null || step.id().isBlank() ? "step" + (index + 1) : step.id());
            pipelineStep.put("definition_ref", reference);
            pipelineStep.put("input", step.input() == null ? defaultInput(index, pipelineSteps) : step.input());
            pipelineSteps.add(pipelineStep);
        }
        Map<String, Object> pipeline = definitionEnvelope(DefinitionKind.CAPABILITY_PIPELINE, pipelineId,
                Map.of("title", request.name(), "steps", pipelineSteps));
        Map<String, Object> workflow = definitionEnvelope(DefinitionKind.WORKFLOW, workflowId,
                Map.of("title", request.name(), "capability_pipeline_ref", Map.of("kind", "capability_pipeline", "id", pipelineId, "version", 1),
                        "input_schema", Map.of("type", "object"), "output", Map.of("type", "object")));
        DefinitionDocument pipelineDocument = document(pipeline, DefinitionKind.CAPABILITY_PIPELINE, pipelineId);
        DefinitionDocument workflowDocument = document(workflow, DefinitionKind.WORKFLOW, workflowId);
        definitions.saveIfAbsent(pipelineDocument);
        definitions.saveIfAbsent(workflowDocument);
        registry.register(pipelineDocument);
        registry.register(workflowDocument);
        return new CustomWorkflowResponse(workflowId, pipelineId, 1, request.steps().size());
    }

    private Map<String, Object> defaultInput(int index, List<Map<String, Object>> previous) {
        if (index == 0) return Map.of("input", "$run.input");
        Map<String, Object> prior = previous.get(index - 1);
        return Map.of("input", "$step." + prior.get("id") + ".output");
    }

    private Map<String, Object> definitionEnvelope(DefinitionKind kind, String id, Map<String, Object> content) {
        Map<String, Object> result = new LinkedHashMap<>(content);
        result.put("kind", kind.value());
        result.put("id", id);
        result.put("version", 1);
        result.put("schema_version", 1);
        result.put("status", "active");
        return result;
    }

    private DefinitionDocument document(Map<String, Object> content, DefinitionKind kind, String id) {
        return new DefinitionDocument(new DefinitionKey(kind, id, 1), 1, DefinitionStatus.ACTIVE,
                content, checksum(content), "custom-workbench");
    }

    private String checksum(Map<String, Object> content) {
        try {
            byte[] value = mapper.writer().with(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                    .writeValueAsBytes(content);
            return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (JsonProcessingException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("Cannot calculate workflow checksum", exception);
        }
    }

    private String slug(String value) {
        String slug = value.toLowerCase().replaceAll("[^a-z0-9]+", "-").replaceAll("^-|-$", "");
        return slug.isBlank() ? "workflow" : slug.substring(0, Math.min(slug.length(), 30));
    }

    public record CustomWorkflowRequest(String name, List<CustomStep> steps) { }
    public record CustomStep(String id, String toolId, Integer toolVersion, Map<String, Object> input) { }
    public record CustomWorkflowResponse(String workflowId, String pipelineId, int version, int stepCount) { }
}
