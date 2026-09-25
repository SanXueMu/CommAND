package com.zthcpa.command.persistence.run;

import com.zthcpa.command.persistence.step.CleanStepSnapshot;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record CleanRunSnapshot(
        String id,
        String workflowId,
        int workflowVersion,
        Map<String, Object> input,
        String status,
        Map<String, Object> error,
        Instant createdAt,
        Instant finishedAt,
        List<CleanStepSnapshot> steps
) {
    public CleanRunSnapshot {
        steps = List.copyOf(steps);
    }
}
