package com.zthcpa.command.run;

import com.zthcpa.command.contract.ToolKey;

import java.util.Map;
import java.util.Objects;

public final class TaskLifecycle {
    private TaskSnapshot current;

    public TaskLifecycle(String handle, ToolKey tool, Map<String, Object> input, int maxAttempts) {
        this.current = new TaskSnapshot(
                handle,
                tool,
                TaskStatus.QUEUED,
                input,
                null,
                null,
                1,
                maxAttempts
        );
    }

    public synchronized TaskSnapshot snapshot() {
        return current;
    }

    public synchronized TaskSnapshot start() {
        return transition(TaskStatus.RUNNING, null, null, current.attempt());
    }

    public synchronized TaskSnapshot pause() {
        return transition(TaskStatus.PAUSED, null, null, current.attempt());
    }

    public synchronized TaskSnapshot resume() {
        return transition(TaskStatus.QUEUED, null, null, current.attempt());
    }

    public synchronized TaskSnapshot requeue() {
        if (current.attempt() >= current.maxAttempts()) {
            throw new InvalidRunTransitionException(
                    "Task retry limit reached: " + current.handle()
            );
        }
        return transition(TaskStatus.QUEUED, null, null, current.attempt() + 1);
    }

    public synchronized TaskSnapshot succeed(Map<String, Object> output) {
        return transition(TaskStatus.SUCCEEDED, output, null, current.attempt());
    }

    public synchronized TaskSnapshot fail(Map<String, Object> error) {
        return transition(TaskStatus.FAILED, null, error, current.attempt());
    }

    public synchronized TaskSnapshot failReview(Map<String, Object> error) {
        return transition(TaskStatus.FAILED_REVIEW, null, error, current.attempt());
    }

    public synchronized TaskSnapshot cancel() {
        return transition(TaskStatus.CANCELLED, null, null, current.attempt());
    }

    public synchronized TaskSnapshot interrupt() {
        return transition(TaskStatus.INTERRUPTED, null, null, current.attempt());
    }

    private TaskSnapshot transition(
            TaskStatus next,
            Map<String, Object> output,
            Map<String, Object> error,
            int attempt
    ) {
        RunStateMachine.requireTransition(current.status(), next);
        current = new TaskSnapshot(
                current.handle(),
                current.tool(),
                next,
                current.input(),
                output,
                error,
                attempt,
                current.maxAttempts()
        );
        return current;
    }
}
