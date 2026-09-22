package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionKey;

import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public final class RunLifecycle {
    private final Clock clock;
    private RunSnapshot current;

    public RunLifecycle(
            String id,
            DefinitionKey workflow,
            Map<String, Object> input,
            Clock clock
    ) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.current = new RunSnapshot(id, workflow, RunStatus.RUNNING, input, null, now(), null);
    }

    public synchronized RunSnapshot snapshot() {
        return current;
    }

    public synchronized RunSnapshot pause() {
        return transition(RunStatus.PAUSED, null);
    }

    public synchronized RunSnapshot resume() {
        return transition(RunStatus.RUNNING, null);
    }

    public synchronized RunSnapshot succeed() {
        return transition(RunStatus.SUCCEEDED, null);
    }

    public synchronized RunSnapshot fail(Map<String, Object> error) {
        return transition(RunStatus.FAILED, error);
    }

    public synchronized RunSnapshot cancel() {
        return transition(RunStatus.CANCELLED, null);
    }

    public synchronized RunSnapshot interrupt() {
        return transition(RunStatus.INTERRUPTED, null);
    }

    private RunSnapshot transition(RunStatus next, Map<String, Object> error) {
        RunStateMachine.requireTransition(current.status(), next);
        Instant finishedAt = next.terminal() ? now() : null;
        current = new RunSnapshot(
                current.id(),
                current.workflow(),
                next,
                current.input(),
                error,
                current.createdAt(),
                finishedAt
        );
        return current;
    }

    private Instant now() {
        return clock.instant();
    }
}
