package com.zthcpa.command.runtime;

import java.util.Map;

public record WorkerJobRequest(
        String toolId,
        String taskId,
        int attempt,
        Map<String, Object> input
) {
}
