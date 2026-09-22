package com.zthcpa.command.run;

import java.util.EnumSet;

public enum RunStatus {
    RUNNING,
    PAUSED,
    SUCCEEDED,
    FAILED,
    FAILED_REVIEW,
    CANCELLED,
    INTERRUPTED;

    public boolean terminal() {
        return EnumSet.of(SUCCEEDED, FAILED, FAILED_REVIEW, CANCELLED, INTERRUPTED).contains(this);
    }

    public boolean canTransitionTo(RunStatus next) {
        return switch (this) {
            case RUNNING -> EnumSet.of(PAUSED, SUCCEEDED, FAILED, FAILED_REVIEW, CANCELLED, INTERRUPTED).contains(next);
            case PAUSED -> EnumSet.of(RUNNING, FAILED, FAILED_REVIEW, CANCELLED).contains(next);
            case INTERRUPTED -> next == RUNNING;
            default -> false;
        };
    }
}
