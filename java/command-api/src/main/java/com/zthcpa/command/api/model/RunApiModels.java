package com.zthcpa.command.api.model;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class RunApiModels {
    private RunApiModels() {
    }

    public record SubmitRunRequest(String workflowId, Integer workflowVersion, Map<String, Object> input) {
    }

    public record SubmitRunResponse(String runId, String status, String firstTaskHandle) {
    }

    public record RunResponse(
            String runId,
            String displayId,
            String workflowId,
            String workflowName,
            int workflowVersion,
            String status,
            String statusLabel,
            Instant createdAt,
            Instant finishedAt,
            List<StepResponse> steps,
            int completedSteps,
            int totalSteps,
            int progressPercent,
            String currentStep
    ) {
    }

    public record RunListResponse(List<RunResponse> items, long total, int offset, int limit) { }

    public record StepResponse(int index, String status, TaskResponse task) {
    }

    public record TaskResponse(
            int attempt,
            int maxAttempts,
            String status,
            Instant startedAt,
            Instant finishedAt,
            Map<String, Object> input,
            Map<String, Object> output,
            Map<String, Object> error
    ) {
    }

    public record RunEventResponse(
            long id,
            String runId,
            String stepId,
            String kind,
            String actor,
            Map<String, Object> detail,
            Instant createdAt
    ) {
    }

    public record ErrorResponse(String code, String message) {
    }
}
