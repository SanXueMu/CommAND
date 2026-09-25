package com.zthcpa.command.persistence.event;

import java.time.Instant;
import java.util.Map;

public record CleanTaskEvent(
        long id,
        String taskId,
        String kind,
        Map<String, Object> detail,
        Instant createdAt
) {
}
