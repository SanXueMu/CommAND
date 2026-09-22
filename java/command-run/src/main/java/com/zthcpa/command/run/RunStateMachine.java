package com.zthcpa.command.run;

public final class RunStateMachine {
    private RunStateMachine() {
    }

    public static void requireTransition(RunStatus current, RunStatus next) {
        if (!current.canTransitionTo(next)) {
            throw new InvalidRunTransitionException(
                    "Invalid run transition: " + current + " -> " + next
            );
        }
    }

    public static void requireTransition(TaskStatus current, TaskStatus next) {
        if (!current.canTransitionTo(next)) {
            throw new InvalidRunTransitionException(
                    "Invalid task transition: " + current + " -> " + next
            );
        }
    }
}
