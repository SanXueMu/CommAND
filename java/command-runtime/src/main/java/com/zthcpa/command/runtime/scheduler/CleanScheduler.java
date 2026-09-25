package com.zthcpa.command.runtime.scheduler;

import com.zthcpa.command.runtime.dispatch.TaskDispatcher;

import java.util.Objects;

/** Executes one bounded claim-and-dispatch cycle for a clean task queue. */
public final class CleanScheduler {
    private final TaskDispatcher dispatcher;

    public CleanScheduler(TaskDispatcher dispatcher) {
        this.dispatcher = Objects.requireNonNull(dispatcher, "dispatcher");
    }

    public PollResult pollOnce(String workerId) {
        if (workerId == null || workerId.isBlank()) {
            throw new IllegalArgumentException("workerId must not be blank");
        }
        return new PollResult(workerId, dispatcher.dispatchNext(workerId));
    }

    public record PollResult(String workerId, boolean dispatched) {
    }
}
