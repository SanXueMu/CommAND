package com.zthcpa.command.persistence.task;

import com.zthcpa.command.run.TaskStatus;

import java.util.Map;

public record CleanTaskRow(
        String id,
        String stepId,
        String toolId,
        int toolVersion,
        int attempt,
        int maxAttempts,
        String workerId,
        Map<String, Object> input,
        Map<String, Object> output,
        Map<String, Object> error,
        TaskStatus status
) {
}
