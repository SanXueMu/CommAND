package com.zthcpa.command.persistence.run;

import com.zthcpa.command.run.RunStatus;

import java.time.Instant;
import java.util.Map;

public record RunRow(
        String id,
        String pipelineId,
        Map<String, Object> input,
        RunStatus status,
        Map<String, Object> error,
        Instant createdAt,
        Instant finishedAt
) {
}
