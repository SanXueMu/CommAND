package com.zthcpa.command.persistence;

import com.zthcpa.command.run.RunStatus;

public record RunStatusChange(String runId, RunStatus expected, RunStatus next) {
    public RunStatusChange {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        if (expected == null || next == null) {
            throw new NullPointerException("Run statuses must not be null");
        }
    }
}
