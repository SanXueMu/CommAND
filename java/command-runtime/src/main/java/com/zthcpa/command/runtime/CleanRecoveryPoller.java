package com.zthcpa.command.runtime;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class CleanRecoveryPoller {
    private final StaleTaskRecoveryPort recovery;
    private final Clock clock;
    private final Duration staleAfter;
    private final int batchSize;

    public CleanRecoveryPoller(
            StaleTaskRecoveryPort recovery,
            Clock clock,
            Duration staleAfter,
            int batchSize
    ) {
        this.recovery = Objects.requireNonNull(recovery, "recovery");
        this.clock = Objects.requireNonNull(clock, "clock");
        if (staleAfter == null || staleAfter.isNegative() || staleAfter.isZero()) {
            throw new IllegalArgumentException("staleAfter must be positive");
        }
        if (batchSize < 1 || batchSize > 1000) {
            throw new IllegalArgumentException("batchSize must be between 1 and 1000");
        }
        this.staleAfter = staleAfter;
        this.batchSize = batchSize;
    }

    public int pollOnce() {
        return recovery.recoverStaleTasks(Instant.now(clock).minus(staleAfter), batchSize);
    }
}
