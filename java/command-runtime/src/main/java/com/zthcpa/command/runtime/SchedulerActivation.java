package com.zthcpa.command.runtime;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** Explicitly activates a scheduler only after the Worker passes health verification. */
public final class SchedulerActivation implements AutoCloseable {
    private final WorkerHealthChecker healthChecker;
    private final CleanSchedulerLoop loop;
    private final AtomicBoolean active = new AtomicBoolean();

    public SchedulerActivation(WorkerHealthChecker healthChecker, CleanSchedulerLoop loop) {
        this.healthChecker = Objects.requireNonNull(healthChecker, "healthChecker");
        this.loop = Objects.requireNonNull(loop, "loop");
    }

    public void activate() {
        if (!active.compareAndSet(false, true)) {
            throw new IllegalStateException("Scheduler activation is already active");
        }
        try {
            healthChecker.verify();
            loop.start();
        } catch (RuntimeException exception) {
            active.set(false);
            throw exception;
        }
    }

    public void deactivate() {
        if (active.compareAndSet(true, false)) {
            loop.stop();
        }
    }

    public boolean isActive() {
        return active.get();
    }

    @Override
    public void close() {
        deactivate();
        loop.close();
    }
}
