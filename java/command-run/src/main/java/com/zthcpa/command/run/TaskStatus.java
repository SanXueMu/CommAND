package com.zthcpa.command.run;

import java.util.EnumSet;

public enum TaskStatus {
    QUEUED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    FAILED_REVIEW,
    CANCELLED,
    INTERRUPTED,
    PAUSED;

    public boolean terminal() {
        return EnumSet.of(SUCCEEDED, FAILED, FAILED_REVIEW, CANCELLED, INTERRUPTED).contains(this);
    }

    public boolean canTransitionTo(TaskStatus next) {
        return switch (this) {
            case QUEUED -> EnumSet.of(RUNNING, CANCELLED, INTERRUPTED).contains(next);
            case RUNNING -> EnumSet.of(QUEUED, SUCCEEDED, FAILED, FAILED_REVIEW, CANCELLED, INTERRUPTED, PAUSED).contains(next);
            case PAUSED -> EnumSet.of(QUEUED, RUNNING, CANCELLED, INTERRUPTED).contains(next);
            case INTERRUPTED -> EnumSet.of(QUEUED, RUNNING).contains(next);
            default -> false;
        };
    }
}
