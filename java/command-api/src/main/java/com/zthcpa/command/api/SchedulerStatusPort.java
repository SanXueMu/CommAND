package com.zthcpa.command.api;

import java.time.Instant;

public interface SchedulerStatusPort {
    Status status();

    record Status(
            boolean enabled,
            boolean active,
            long polls,
            long dispatched,
            long idle,
            long errors,
            Instant lastPollAt,
            ErrorStatus lastError
    ) {
    }

    record ErrorStatus(String type, String message) {
    }
}
