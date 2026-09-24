package com.zthcpa.command.api;

import org.springframework.context.annotation.Conditional;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import static com.zthcpa.command.api.RunApiModels.RunEventResponse;

@Service
@Conditional(DataSourcePresentCondition.class)
public final class RunEventStreamService implements AutoCloseable {
    private static final long POLL_MILLIS = 250;
    private static final long TIMEOUT_MILLIS = 30 * 60 * 1000;

    private final RunApplicationService runs;
    private final ScheduledExecutorService executor = Executors.newScheduledThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "command-run-events");
        thread.setDaemon(true);
        return thread;
    });

    public RunEventStreamService(RunApplicationService runs) {
        this.runs = Objects.requireNonNull(runs, "runs");
    }

    public SseEmitter open(String runId, long afterId) {
        if (runId == null || runId.isBlank()) {
            throw new IllegalArgumentException("Run id must not be blank");
        }
        if (afterId < 0) {
            throw new IllegalArgumentException("afterId must not be negative");
        }
        if (runs.get(runId) == null) {
            return null;
        }

        SseEmitter emitter = new SseEmitter(TIMEOUT_MILLIS);
        AtomicLong cursor = new AtomicLong(afterId);
        ScheduledFuture<?> polling = executor.scheduleWithFixedDelay(
                () -> poll(runId, emitter, cursor), 0, POLL_MILLIS, TimeUnit.MILLISECONDS
        );
        Runnable cancel = () -> polling.cancel(false);
        emitter.onCompletion(cancel);
        emitter.onTimeout(() -> {
            cancel.run();
            emitter.complete();
        });
        emitter.onError(exception -> cancel.run());
        return emitter;
    }

    private void poll(String runId, SseEmitter emitter, AtomicLong cursor) {
        try {
            List<RunEventResponse> events = runs.events(runId, cursor.get(), 100);
            if (events == null) {
                emitter.complete();
                return;
            }
            for (RunEventResponse event : events) {
                emitter.send(SseEmitter.event()
                        .id(String.valueOf(event.id()))
                        .name(event.kind())
                        .data(event));
                cursor.set(event.id());
            }
            RunApiModels.RunResponse run = runs.get(runId);
            if (events.isEmpty() && run != null && isTerminal(run.status())) {
                emitter.complete();
            }
        } catch (IOException | RuntimeException exception) {
            emitter.completeWithError(exception);
        }
    }

    private static boolean isTerminal(String status) {
        return switch (status) {
            case "succeeded", "failed", "failed_review", "cancelled", "interrupted" -> true;
            default -> false;
        };
    }

    @Override
    public void close() {
        executor.shutdownNow();
    }
}
