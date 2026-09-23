package com.zthcpa.command.runtime;

import java.util.Map;

public record WorkerJob(
        String jobId,
        String status,
        Map<String, Object> output,
        Map<String, Object> error
) {
}
