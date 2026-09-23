package com.zthcpa.command.persistence;

import java.time.Instant;
import java.util.Map;

public record CleanArtifact(
        String id,
        String runId,
        String stepId,
        String kind,
        String storageKey,
        String mediaType,
        Long sizeBytes,
        String checksum,
        Map<String, Object> metadata,
        Instant createdAt
) {
}
