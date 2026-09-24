package com.zthcpa.command.runtime;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public final class RecoveryMetrics {
    private final LongAdder polls = new LongAdder();
    private final LongAdder recovered = new LongAdder();
    private final LongAdder errors = new LongAdder();
    private final AtomicReference<Instant> lastPollAt = new AtomicReference<>();
    private final AtomicReference<Integer> lastRecovered = new AtomicReference<>();
    private final AtomicReference<ErrorSnapshot> lastError = new AtomicReference<>();

    void recordPoll(Instant at, int recoveredCount) {
        polls.increment();
        recovered.add(recoveredCount);
        lastRecovered.set(recoveredCount);
        lastPollAt.set(at);
    }

    void recordError(Instant at, RuntimeException exception) {
        errors.increment();
        lastPollAt.set(at);
        lastError.set(new ErrorSnapshot(
                exception.getClass().getSimpleName(), exception.getMessage()
        ));
    }

    public Snapshot snapshot(boolean active) {
        return new Snapshot(
                polls.sum(), recovered.sum(), errors.sum(), lastPollAt.get(),
                lastRecovered.get(), lastError.get(), active
        );
    }

    public record Snapshot(
            long polls,
            long recovered,
            long errors,
            Instant lastPollAt,
            Integer lastRecovered,
            ErrorSnapshot lastError,
            boolean active
    ) {
    }

    public record ErrorSnapshot(String type, String message) {
    }
}
