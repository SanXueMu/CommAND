package com.zthcpa.command.persistence;

import java.time.Instant;
import java.util.Map;

public record CleanTaskSnapshot(
        String id,
        int attempt,
        int maxAttempts,
        String workerId,
        Map<String, Object> input,
        Map<String, Object> output,
        Map<String, Object> error,
        String status,
        Instant heartbeatAt,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt
) {
}
