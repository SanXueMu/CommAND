package com.zthcpa.command.persistence.task;

import com.zthcpa.command.run.TaskStatus;

import java.util.Map;

public record TaskRow(
        String handle,
        String toolId,
        Map<String, Object> input,
        Map<String, Object> output,
        TaskStatus status,
        Map<String, Object> error,
        String pipelineRun,
        int stepIndex,
        int attempt,
        int maxAttempts
) {
}
