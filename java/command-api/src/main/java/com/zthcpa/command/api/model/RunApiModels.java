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
            String workflowId,
            int workflowVersion,
            String status,
            Instant createdAt,
            Instant finishedAt,
            List<StepResponse> steps
    ) {
    }

    public record StepResponse(int index, String status, TaskResponse task) {
    }

    public record TaskResponse(int attempt, int maxAttempts, String status, Instant startedAt, Instant finishedAt) {
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
