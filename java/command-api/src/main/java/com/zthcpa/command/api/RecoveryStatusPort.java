package com.zthcpa.command.api;

import java.time.Instant;

public interface RecoveryStatusPort {
    Status status();

    record Status(
            boolean enabled,
            boolean active,
            long polls,
            long recovered,
            long errors,
            Instant lastPollAt,
            Integer lastRecovered,
            ErrorStatus lastError
    ) {
    }

    record ErrorStatus(String type, String message) {
    }
}
