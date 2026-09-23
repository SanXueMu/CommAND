package com.zthcpa.command.runtime;

import java.util.List;
import java.time.Duration;
import java.util.Map;
import java.util.function.LongSupplier;

public final class TaskDispatcher {
    private static final Duration DEFAULT_POLL_INTERVAL = Duration.ofMillis(250);
    private static final Duration DEFAULT_JOB_TIMEOUT = Duration.ofMinutes(30);
    private static final Duration DEFAULT_HEARTBEAT_INTERVAL = Duration.ofSeconds(30);

    private final TaskExecutionPort tasks;
    private final WorkerRuntime worker;
    private final Duration pollInterval;
    private final Duration jobTimeout;
    private final Duration heartbeatInterval;
    private final Sleeper sleeper;
    private final LongSupplier nanoTime;

    public TaskDispatcher(TaskExecutionPort tasks, WorkerRuntime worker) {
        this(tasks, worker, DEFAULT_POLL_INTERVAL, DEFAULT_JOB_TIMEOUT, DEFAULT_HEARTBEAT_INTERVAL);
    }

    public TaskDispatcher(
            TaskExecutionPort tasks,
            WorkerRuntime worker,
            Duration pollInterval,
            Duration jobTimeout
    ) {
        this(tasks, worker, pollInterval, jobTimeout, DEFAULT_HEARTBEAT_INTERVAL, Thread::sleep, System::nanoTime);
    }

    public TaskDispatcher(
            TaskExecutionPort tasks,
            WorkerRuntime worker,
            Duration pollInterval,
            Duration jobTimeout,
            Duration heartbeatInterval
    ) {
        this(tasks, worker, pollInterval, jobTimeout, heartbeatInterval, Thread::sleep, System::nanoTime);
    }

    TaskDispatcher(
            TaskExecutionPort tasks,
            WorkerRuntime worker,
            Duration pollInterval,
            Duration jobTimeout,
            Sleeper sleeper,
            LongSupplier nanoTime
    ) {
        this(tasks, worker, pollInterval, jobTimeout, DEFAULT_HEARTBEAT_INTERVAL, sleeper, nanoTime);
    }

    TaskDispatcher(
            TaskExecutionPort tasks,
            WorkerRuntime worker,
            Duration pollInterval,
            Duration jobTimeout,
            Duration heartbeatInterval,
            Sleeper sleeper,
            LongSupplier nanoTime
    ) {
        this.tasks = tasks;
        this.worker = worker;
        if (pollInterval == null || pollInterval.isNegative() || pollInterval.isZero()) {
            throw new IllegalArgumentException("pollInterval must be positive");
        }
        if (jobTimeout == null || jobTimeout.isNegative() || jobTimeout.isZero()) {
            throw new IllegalArgumentException("jobTimeout must be positive");
        }
        if (heartbeatInterval == null || heartbeatInterval.isNegative() || heartbeatInterval.isZero()) {
            throw new IllegalArgumentException("heartbeatInterval must be positive");
        }
        if (heartbeatInterval.compareTo(jobTimeout) >= 0) {
            throw new IllegalArgumentException("heartbeatInterval must be shorter than jobTimeout");
        }
        this.pollInterval = pollInterval;
        this.jobTimeout = jobTimeout;
        this.heartbeatInterval = heartbeatInterval;
        this.sleeper = sleeper;
        this.nanoTime = nanoTime;
    }

    public boolean dispatchNext(String workerId) {
        TaskExecutionPort.TaskExecution task = tasks.claim(workerId);
        if (task == null) {
            return false;
        }
        WorkerJob job = null;
        JobPolling polling = null;
        try {
            job = worker.createJob(task.toolId(), new WorkerJobRequest(
                    task.toolId(), task.taskId(), task.attempt(), task.input()
            ));
            polling = new JobPolling(job);
            WorkerJob finalJob = awaitTerminal(task.taskId(), workerId, polling);
            switch (finalJob.status()) {
                case "succeeded" -> tasks.succeed(task.taskId(), workerId, finalJob.output());
                case "cancelled" -> {
                    if (!tasks.isCancellationRequested(task.taskId(), workerId)) {
                        tasks.cancel(task.taskId(), workerId, finalJob.error());
                    }
                }
                case "failed", "failed_review" -> tasks.fail(task.taskId(), workerId, finalJob.error());
                default -> throw new WorkerRuntimeException("Worker job did not reach terminal state: " + finalJob.status());
            }
            return true;
        } catch (WorkerRuntimeException exception) {
            if (job != null && (polling == null || !polling.cancelSent)) {
                try {
                    worker.cancelJob(job.jobId());
                } catch (WorkerRuntimeException cancelException) {
                    exception.addSuppressed(cancelException);
                }
            }
            tasks.fail(task.taskId(), workerId, Map.of(
                    "code", "WORKER_RUNTIME_ERROR", "message", exception.getMessage()
            ));
            throw exception;
        }
    }

    private WorkerJob awaitTerminal(String taskId, String workerId, JobPolling polling) {
        long cursor = 0;
        long deadline = nanoTime.getAsLong() + jobTimeout.toNanos();
        long lastHeartbeat = nanoTime.getAsLong();
        WorkerJob current = polling.created;
        while (true) {
            cursor = relayEvents(taskId, current.jobId(), cursor);
            if (!polling.cancelSent && tasks.isCancellationRequested(taskId, workerId)) {
                worker.cancelJob(current.jobId());
                polling.cancelSent = true;
            }
            long now = nanoTime.getAsLong();
            if (!polling.cancelSent && now - lastHeartbeat >= heartbeatInterval.toNanos()) {
                if (!tasks.heartbeat(taskId, workerId)) {
                    throw new WorkerRuntimeException("Task worker ownership lost: " + taskId);
                }
                lastHeartbeat = now;
            }
            current = worker.getJob(current.jobId());
            if (isTerminal(current.status())) {
                relayEvents(taskId, current.jobId(), cursor);
                return current;
            }
            if (!"queued".equals(current.status()) && !"running".equals(current.status())) {
                throw new WorkerRuntimeException("Worker job returned unknown state: " + current.status());
            }
            if (nanoTime.getAsLong() >= deadline) {
                throw new WorkerRuntimeException("Worker job timed out: " + current.jobId());
            }
            sleep();
        }
    }

    private long relayEvents(String taskId, String jobId, long afterSequence) {
        List<WorkerEvent> events = worker.listEvents(jobId, afterSequence);
        long cursor = afterSequence;
        for (WorkerEvent event : events) {
            if (event.sequence() <= cursor) {
                continue;
            }
            tasks.recordWorkerEvent(taskId, event);
            cursor = event.sequence();
        }
        return cursor;
    }

    private void sleep() {
        try {
            sleeper.sleep(pollInterval.toMillis());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new WorkerRuntimeException("Worker job polling interrupted", exception);
        }
    }

    private static boolean isTerminal(String status) {
        return "succeeded".equals(status)
                || "failed".equals(status)
                || "failed_review".equals(status)
                || "cancelled".equals(status);
    }

    @FunctionalInterface
    interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    private static final class JobPolling {
        private final WorkerJob created;
        private boolean cancelSent;

        private JobPolling(WorkerJob created) {
            this.created = created;
        }
    }
}
