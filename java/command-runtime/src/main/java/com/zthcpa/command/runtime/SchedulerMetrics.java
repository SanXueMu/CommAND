package com.zthcpa.command.runtime;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public final class SchedulerMetrics {
    private final LongAdder polls = new LongAdder();
    private final LongAdder dispatched = new LongAdder();
    private final LongAdder idle = new LongAdder();
    private final LongAdder errors = new LongAdder();
    private final AtomicReference<Instant> lastPollAt = new AtomicReference<>();
    private final AtomicReference<ErrorSnapshot> lastError = new AtomicReference<>();

    void recordPoll(Instant at, boolean didDispatch) {
        polls.increment();
        if (didDispatch) {
            dispatched.increment();
        } else {
            idle.increment();
        }
        lastPollAt.set(at);
    }

    void recordError(Instant at, RuntimeException exception) {
        errors.increment();
        lastPollAt.set(at);
        lastError.set(new ErrorSnapshot(exception.getClass().getSimpleName(), exception.getMessage()));
    }

    public Snapshot snapshot(boolean active) {
        return new Snapshot(
                polls.sum(),
                dispatched.sum(),
                idle.sum(),
                errors.sum(),
                lastPollAt.get(),
                lastError.get(),
                active
        );
    }

    public record Snapshot(
            long polls,
            long dispatched,
            long idle,
            long errors,
            Instant lastPollAt,
            ErrorSnapshot lastError,
            boolean active
    ) {
    }

    public record ErrorSnapshot(String type, String message) {
    }
}
