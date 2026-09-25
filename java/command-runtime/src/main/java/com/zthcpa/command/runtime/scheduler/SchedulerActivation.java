package com.zthcpa.command.runtime.scheduler;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/** Explicitly activates a scheduler only after configured readiness checks pass. */
public final class SchedulerActivation implements AutoCloseable {
    private final Runnable readinessCheck;
    private final CleanSchedulerLoop loop;
    private final AtomicBoolean active = new AtomicBoolean();

    public SchedulerActivation(Runnable readinessCheck, CleanSchedulerLoop loop) {
        this.readinessCheck = Objects.requireNonNull(readinessCheck, "readinessCheck");
        this.loop = Objects.requireNonNull(loop, "loop");
    }

    public void activate() {
        if (!active.compareAndSet(false, true)) {
            throw new IllegalStateException("Scheduler activation is already active");
        }
        try {
            readinessCheck.run();
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
