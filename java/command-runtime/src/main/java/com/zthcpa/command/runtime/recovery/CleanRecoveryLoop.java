package com.zthcpa.command.runtime.recovery;

import java.time.Duration;
import java.util.Objects;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/** Owns the optional background lifecycle around stale-task recovery polls. */
public final class CleanRecoveryLoop implements AutoCloseable {
    private final CleanRecoveryPoller poller;
    private final Duration interval;
    private final Consumer<RuntimeException> errorHandler;
    private final RecoveryMetrics metrics;
    private final ExecutorService executor;
    private final AtomicBoolean running = new AtomicBoolean();
    private final CountDownLatch stopped = new CountDownLatch(1);

    public CleanRecoveryLoop(
            CleanRecoveryPoller poller,
            Duration interval,
            Consumer<RuntimeException> errorHandler
    ) {
        this(poller, interval, errorHandler, new RecoveryMetrics());
    }

    public CleanRecoveryLoop(
            CleanRecoveryPoller poller,
            Duration interval,
            Consumer<RuntimeException> errorHandler,
            RecoveryMetrics metrics
    ) {
        this.poller = Objects.requireNonNull(poller, "poller");
        if (interval == null || interval.isNegative() || interval.isZero()) {
            throw new IllegalArgumentException("interval must be positive");
        }
        this.interval = interval;
        this.errorHandler = Objects.requireNonNull(errorHandler, "errorHandler");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.executor = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "command-clean-recovery");
            thread.setDaemon(true);
            return thread;
        });
    }

    public void start() {
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("Recovery loop is already running");
        }
        executor.submit(this::runLoop);
    }

    public void stop() {
        if (running.compareAndSet(true, false)) {
            List<Runnable> pending = executor.shutdownNow();
            if (!pending.isEmpty()) {
                stopped.countDown();
            }
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

    public boolean isRunning() {
        return running.get();
    }

    public RecoveryMetrics.Snapshot metrics() {
        return metrics.snapshot(running.get());
    }

    private void runLoop() {
        try {
            while (running.get()) {
                try {
                    int recovered = poller.pollOnce();
                    metrics.recordPoll(java.time.Instant.now(), recovered);
                } catch (RuntimeException exception) {
                    metrics.recordError(java.time.Instant.now(), exception);
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
