package com.zthcpa.command.runtime;

import com.zthcpa.command.tools.JavaTool;
import com.zthcpa.command.tools.JavaToolRegistry;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;

/** Executes Java tools asynchronously behind the same handle protocol as HTTP workers. */
public final class InProcessToolRuntime implements WorkerRuntime, AutoCloseable {
    private final JavaToolRegistry tools;
    private final ExecutorService executor;
    private final Map<String, JobState> jobs = new ConcurrentHashMap<>();

    public InProcessToolRuntime(JavaToolRegistry tools) {
        this(tools, Executors.newCachedThreadPool());
    }

    InProcessToolRuntime(JavaToolRegistry tools, ExecutorService executor) {
        this.tools = tools;
        this.executor = executor;
    }

    @Override
    public WorkerJob createJob(String toolId, WorkerJobRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("Java tool request must not be null");
        }
        JavaTool tool = tools.get(toolId, 1);
        String jobId = "java-" + UUID.randomUUID();
        JobState state = new JobState(jobId);
        jobs.put(jobId, state);
        state.status = "running";
        state.emit("started", Map.of("tool", toolId, "task_id", request.taskId()));
        state.future = executor.submit(() -> execute(tool, request, state));
        return state.snapshot();
    }

    @Override
    public WorkerJob getJob(String jobId) {
        return state(jobId).snapshot();
    }

    @Override
    public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
        if (afterSequence < 0) {
            throw new IllegalArgumentException("After sequence must not be negative");
        }
        return state(jobId).eventsAfter(afterSequence);
    }

    @Override
    public void cancelJob(String jobId) {
        JobState state = state(jobId);
        state.cancelRequested = true;
        Future<?> future = state.future;
        if (future != null) {
            future.cancel(true);
        }
        if (!isTerminal(state.status)) {
            state.status = "cancelled";
            state.emit("cancelled", Map.of());
        }
    }

    @Override
    public void close() {
        executor.shutdownNow();
    }

    private void execute(JavaTool tool, WorkerJobRequest request, JobState state) {
        try {
            Map<String, Object> output = tool.execute(request.input(), event -> {
                if (state.cancelRequested || Thread.currentThread().isInterrupted()) {
                    throw new WorkerRuntimeException("Java tool job cancelled: " + state.jobId);
                }
                state.emit("progress", event);
            });
            if (!state.cancelRequested) {
                state.output = output;
                state.status = "succeeded";
                state.emit("succeeded", Map.of());
            }
        } catch (RuntimeException exception) {
            if (!state.cancelRequested) {
                state.error = Map.of("code", "JAVA_TOOL_ERROR", "message", safeMessage(exception));
                state.status = "failed";
                state.emit("failed", state.error);
            }
        }
    }

    private JobState state(String jobId) {
        JobState state = jobs.get(jobId);
        if (state == null) {
            throw new WorkerRuntimeException("Java tool job not found: " + jobId);
        }
        return state;
    }

    private static boolean isTerminal(String status) {
        return "succeeded".equals(status) || "failed".equals(status) || "cancelled".equals(status);
    }

    private static String safeMessage(RuntimeException exception) {
        String message = exception.getMessage();
        return message == null || message.isBlank() ? exception.getClass().getSimpleName() : message;
    }

    private static final class JobState {
        private final String jobId;
        private final AtomicLong nextSequence = new AtomicLong();
        private final List<WorkerEvent> events = new ArrayList<>();
        private volatile String status = "queued";
        private volatile Map<String, Object> output;
        private volatile Map<String, Object> error;
        private volatile boolean cancelRequested;
        private volatile Future<?> future;

        private JobState(String jobId) {
            this.jobId = jobId;
        }

        private synchronized void emit(String type, Map<String, Object> data) {
            events.add(new WorkerEvent(nextSequence.incrementAndGet(), type, Map.copyOf(data)));
        }

        private synchronized List<WorkerEvent> eventsAfter(long afterSequence) {
            return events.stream()
                    .filter(event -> event.sequence() > afterSequence)
                    .toList();
        }

        private WorkerJob snapshot() {
            return new WorkerJob(jobId, status, output, error);
        }
    }
}
