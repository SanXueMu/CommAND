package com.zthcpa.command.runtime.scheduler;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/** Owns the optional background lifecycle around the stateless scheduler poll. */
public final class CleanSchedulerLoop implements AutoCloseable {
    private final CleanScheduler scheduler;
    private final String workerId;
    private final Duration interval;
    private final Consumer<RuntimeException> errorHandler;
    private final SchedulerMetrics metrics;
    private final ExecutorService executor;
    private final AtomicBoolean running = new AtomicBoolean();
    private final CountDownLatch stopped = new CountDownLatch(1);

    public CleanSchedulerLoop(
            CleanScheduler scheduler,
            String workerId,
            Duration interval,
            Consumer<RuntimeException> errorHandler
    ) {
        this(scheduler, workerId, interval, errorHandler, new SchedulerMetrics());
    }

    public CleanSchedulerLoop(
            CleanScheduler scheduler,
            String workerId,
            Duration interval,
            Consumer<RuntimeException> errorHandler,
            SchedulerMetrics metrics
    ) {
        this.scheduler = Objects.requireNonNull(scheduler, "scheduler");
        if (workerId == null || workerId.isBlank()) {
            throw new IllegalArgumentException("workerId must not be blank");
        }
        if (interval == null || interval.isNegative() || interval.isZero()) {
            throw new IllegalArgumentException("interval must be positive");
        }
        this.workerId = workerId;
        this.interval = interval;
        this.errorHandler = Objects.requireNonNull(errorHandler, "errorHandler");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.executor = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "command-clean-scheduler-" + workerId);
            thread.setDaemon(true);
            return thread;
        });
    }

    public void start() {
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("Scheduler loop is already running");
        }
        executor.submit(this::runLoop);
    }

    public void stop() {
        if (running.compareAndSet(true, false)) {
            executor.shutdownNow();
            try {
                stopped.await();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public void close() {
        stop();
        executor.shutdownNow();
    }

    private void runLoop() {
        try {
            while (running.get()) {
                try {
                    CleanScheduler.PollResult result = scheduler.pollOnce(workerId);
                    metrics.recordPoll(Instant.now(), result.dispatched());
                } catch (RuntimeException exception) {
                    metrics.recordError(Instant.now(), exception);
                    errorHandler.accept(exception);
                }
                if (!sleepInterval()) {
                    break;
                }
            }
        } finally {
            running.set(false);
            stopped.countDown();
        }
    }

    public SchedulerMetrics.Snapshot metrics() {
        return metrics.snapshot(running.get());
    }

    private boolean sleepInterval() {
        try {
            Thread.sleep(interval.toMillis());
            return true;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
