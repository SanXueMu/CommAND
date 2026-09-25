package com.zthcpa.command.persistence;

import com.zthcpa.command.persistence.run.RunStatusChange;
import com.zthcpa.command.persistence.task.TaskClaim;

import com.zthcpa.command.run.RunStatus;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PersistencePortTest {
    @Test
    void validatesCasRequest() {
        RunStatusChange change = new RunStatusChange("run-1", RunStatus.PAUSED, RunStatus.RUNNING);

        assertEquals("run-1", change.runId());
        assertEquals(RunStatus.PAUSED, change.expected());
        assertThrows(
                IllegalArgumentException.class,
                () -> new RunStatusChange("", RunStatus.RUNNING, RunStatus.PAUSED)
        );
    }

    @Test
    void validatesTaskClaimWorker() {
        assertEquals("worker-1", new TaskClaim("worker-1").workerId());
        assertThrows(IllegalArgumentException.class, () -> new TaskClaim(""));
    }
}
