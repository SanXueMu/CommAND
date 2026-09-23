package com.zthcpa.command.persistence;

import java.time.Instant;
import java.util.Map;

public record CleanRunEvent(
        long id,
        String runId,
        String stepId,
        String kind,
        String actor,
        Map<String, Object> detail,
        Instant createdAt
) {
}
