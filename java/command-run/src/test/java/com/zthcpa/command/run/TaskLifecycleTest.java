package com.zthcpa.command.run;

import com.zthcpa.command.contract.ToolKey;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskLifecycleTest {
    private final ToolKey tool = new ToolKey("ocr.page.extract", 1);

    @Test
    void requeuesRunningTaskAndIncrementsAttempt() {
        TaskLifecycle lifecycle = new TaskLifecycle("task-1", tool, Map.of("page", 1), 2);
        lifecycle.start();
        lifecycle.requeue();

        assertEquals(TaskStatus.QUEUED, lifecycle.snapshot().status());
        assertEquals(2, lifecycle.snapshot().attempt());
    }

    @Test
    void pausedResumeDoesNotConsumeAttempt() {
        TaskLifecycle lifecycle = new TaskLifecycle("task-1", tool, Map.of(), 2);
        lifecycle.start();
        lifecycle.pause();
        lifecycle.resume();

        assertEquals(TaskStatus.QUEUED, lifecycle.snapshot().status());
        assertEquals(1, lifecycle.snapshot().attempt());
    }

    @Test
    void rejectsRetryAtMaximumAttempt() {
        TaskLifecycle lifecycle = new TaskLifecycle("task-1", tool, Map.of(), 1);
        lifecycle.start();

        assertThrows(InvalidRunTransitionException.class, lifecycle::requeue);
    }
}
