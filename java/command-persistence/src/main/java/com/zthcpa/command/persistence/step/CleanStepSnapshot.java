package com.zthcpa.command.persistence.step;

import com.zthcpa.command.persistence.task.CleanTaskSnapshot;

import java.time.Instant;
import java.util.Map;

public record CleanStepSnapshot(
        String id,
        int index,
        String key,
        String definitionKind,
        String definitionId,
        int definitionVersion,
        Map<String, Object> input,
        String status,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt,
        CleanTaskSnapshot latestTask
) {
}
