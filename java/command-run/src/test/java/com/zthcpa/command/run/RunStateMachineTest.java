package com.zthcpa.command.run;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RunStateMachineTest {
    @Test
    void supportsPauseResumeAndTerminalCompletion() {
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(RunStatus.RUNNING, RunStatus.PAUSED));
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(RunStatus.PAUSED, RunStatus.RUNNING));
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(RunStatus.RUNNING, RunStatus.SUCCEEDED));
        assertThrows(
                InvalidRunTransitionException.class,
                () -> RunStateMachine.requireTransition(RunStatus.SUCCEEDED, RunStatus.RUNNING)
        );
    }

    @Test
    void supportsTaskPauseAndRecovery() {
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(TaskStatus.RUNNING, TaskStatus.PAUSED));
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(TaskStatus.PAUSED, TaskStatus.QUEUED));
        assertDoesNotThrow(() -> RunStateMachine.requireTransition(TaskStatus.INTERRUPTED, TaskStatus.RUNNING));
        assertThrows(
                InvalidRunTransitionException.class,
                () -> RunStateMachine.requireTransition(TaskStatus.SUCCEEDED, TaskStatus.FAILED)
        );
    }
}
