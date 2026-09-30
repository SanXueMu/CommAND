package com.zthcpa.command.api.application;

import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.persistence.event.CleanRunEvent;
import com.zthcpa.command.persistence.run.CleanRunQueryRepository;
import com.zthcpa.command.persistence.run.CleanRunSnapshot;
import com.zthcpa.command.persistence.run.CleanRunSubmissionRepository;
import com.zthcpa.command.persistence.run.CleanRecoveryRepository;
import com.zthcpa.command.persistence.task.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.step.CleanStepSnapshot;
import com.zthcpa.command.persistence.task.CleanTaskSnapshot;
import com.zthcpa.command.run.PipelineRunSubmissionPlan;
import com.zthcpa.command.run.RunSubmissionException;
import com.zthcpa.command.run.RunSubmissionPlanner;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.List;
import java.util.UUID;

import static com.zthcpa.command.api.model.RunApiModels.RunResponse;
import static com.zthcpa.command.api.model.RunApiModels.RunEventResponse;
import static com.zthcpa.command.api.model.RunApiModels.StepResponse;
import static com.zthcpa.command.api.model.RunApiModels.SubmitRunResponse;
import static com.zthcpa.command.api.model.RunApiModels.TaskResponse;
import static com.zthcpa.command.api.model.RunApiModels.RunListResponse;

@Service
public final class RunApplicationService {
    private final DefinitionRegistry definitions;
    private final ToolCatalog tools;
    private final CleanRunSubmissionRepository submissions;
    private final CleanRunQueryRepository queries;
    private final CleanRunCompletionRepository completions;
    private final CleanRecoveryRepository recovery;

    public RunApplicationService(
            DefinitionRegistry definitions,
            ToolCatalog tools,
            CleanRunSubmissionRepository submissions,
            CleanRunQueryRepository queries,
            CleanRunCompletionRepository completions,
            CleanRecoveryRepository recovery
    ) {
        this.definitions = definitions;
        this.tools = tools;
        this.submissions = submissions;
        this.queries = queries;
        this.completions = completions;
        this.recovery = recovery;
    }

    public SubmitRunResponse submit(String workflowId, Integer workflowVersion, Map<String, Object> input) {
        PipelineRunSubmissionPlan plan = new RunSubmissionPlanner(
                definitions,
                tools,
                () -> UUID.randomUUID().toString()
        ).planPipeline(workflowId, workflowVersion, input == null ? Map.of() : input);
        submissions.submit(plan);
        return new SubmitRunResponse(plan.runId(), "running", plan.firstTaskId());
    }

    public RunResponse get(String runId) {
        CleanRunSnapshot snapshot = queries.get(runId);
        if (snapshot == null) {
            return null;
        }
        return toRunResponse(snapshot, true);
    }

    private RunResponse toRunResponse(CleanRunSnapshot snapshot, boolean includeSteps) {
        List<StepResponse> steps = snapshot.steps().stream().map(this::toStep).toList();
        int totalSteps = snapshot.steps().size();
        int completedSteps = (int) snapshot.steps().stream().filter(step -> "succeeded".equals(step.status())).count();
        int progress = totalSteps == 0 ? 0 : Math.round(completedSteps * 100f / totalSteps);
        String currentStep = snapshot.steps().stream().filter(step -> !"succeeded".equals(step.status())).findFirst()
                .map(step -> step.definitionId() == null ? step.key() : step.definitionId()).orElse(null);
        return new RunResponse(
                snapshot.id(),
                displayId(snapshot.id()),
                snapshot.workflowId(),
                workflowName(snapshot.workflowId(), snapshot.workflowVersion()),
                snapshot.workflowVersion(),
                snapshot.status(),
                statusLabel(snapshot.status()),
                snapshot.createdAt(),
                snapshot.finishedAt(),
                includeSteps ? steps : List.of(),
                completedSteps,
                totalSteps,
                progress,
                currentStep
        );
    }

    public RunListResponse list(int offset, int limit, String status) {
        return list(offset, limit, status, null, null);
    }

    public RunListResponse list(int offset, int limit, String status, String query, String workflowId) {
        List<RunResponse> items = queries.list(offset, limit, status, query, workflowId).stream()
                .map(snapshot -> toRunResponse(snapshot, false))
                .toList();
        return new RunListResponse(items, queries.count(status, query, workflowId), offset, limit);
    }

    public List<RunEventResponse> events(String runId, long afterId, int limit) {
        if (queries.get(runId) == null) {
            return null;
        }
        return queries.listEvents(runId, afterId, limit).stream().map(this::toEvent).toList();
    }

    public RunResponse cancel(String runId) {
        if (!completions.cancelRun(runId)) return null;
        return get(runId);
    }

    public RunResponse recover(String runId) {
        if (!recovery.recoverInterruptedRun(runId)) return null;
        return get(runId);
    }

    private RunEventResponse toEvent(CleanRunEvent event) {
        return new RunEventResponse(
                event.id(), event.runId(), event.stepId(), event.kind(), event.actor(),
                event.detail(), event.createdAt()
        );
    }

    private StepResponse toStep(CleanStepSnapshot step) {
        CleanTaskSnapshot task = step.latestTask();
        return new StepResponse(step.index(), step.status(), task == null ? null : new TaskResponse(
                task.attempt(), task.maxAttempts(), task.status(), task.startedAt(), task.finishedAt(),
                task.input(), task.output(), task.error()
        ));
    }

    private String displayId(String id) {
        if (id == null || id.length() < 10) return id;
        return "运行-" + id.substring(0, 8);
    }

    private String workflowName(String id, int version) {
        var definition = definitions.getActive(com.zthcpa.command.contract.DefinitionKind.WORKFLOW, id);
        if (definition == null) return id;
        Object title = definition.content().get("title");
        return title instanceof String value && !value.isBlank() ? value : id;
    }

    private String statusLabel(String status) {
        return switch (status) {
            case "queued" -> "排队中";
            case "running" -> "运行中";
            case "succeeded" -> "已完成";
            case "failed" -> "失败";
            case "cancelled" -> "已取消";
            case "interrupted" -> "已中断";
            default -> status;
        };
    }
}
