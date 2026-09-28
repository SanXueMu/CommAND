package com.zthcpa.command.run;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

public final class PipelineExecutionIdentifiers {
    private PipelineExecutionIdentifiers() {
    }

    public static String stepId(String runId, int stepIndex) {
        require(runId, stepIndex);
        return runId + ":step:" + stepIndex;
    }

    public static String taskId(String runId, int stepIndex) {
        require(runId, stepIndex);
        return UUID.nameUUIDFromBytes(
                (runId + ":task:" + stepIndex).getBytes(StandardCharsets.UTF_8)
        ).toString();
    }

    public static String recoveryTaskId(String runId, int stepIndex, int attempt) {
        require(runId, stepIndex);
        if (attempt < 2) {
            throw new IllegalArgumentException("Recovery attempt must be greater than one");
        }
        return UUID.nameUUIDFromBytes(
                (runId + ":task:" + stepIndex + ":attempt:" + attempt).getBytes(StandardCharsets.UTF_8)
        ).toString();
    }

    private static void require(String runId, int stepIndex) {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        if (stepIndex < 0) {
            throw new IllegalArgumentException("Step index must not be negative");
        }
    }
}
