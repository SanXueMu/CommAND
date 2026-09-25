package com.zthcpa.command.runtime.scheduler;

import com.zthcpa.command.runtime.worker.WorkerRuntimeException;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerMetricsTest {
    @Test
    void recordsPollAndErrorCountersInSnapshot() {
        SchedulerMetrics metrics = new SchedulerMetrics();
        Instant first = Instant.parse("2026-09-23T12:00:00Z");
        Instant second = Instant.parse("2026-09-23T12:00:01Z");

        metrics.recordPoll(first, true);
        metrics.recordPoll(second, false);
        metrics.recordError(second, new WorkerRuntimeException("worker unavailable"));

        SchedulerMetrics.Snapshot snapshot = metrics.snapshot(true);

        assertEquals(2, snapshot.polls());
        assertEquals(1, snapshot.dispatched());
        assertEquals(1, snapshot.idle());
        assertEquals(1, snapshot.errors());
        assertEquals(second, snapshot.lastPollAt());
        assertEquals("WorkerRuntimeException", snapshot.lastError().type());
        assertEquals("worker unavailable", snapshot.lastError().message());
        assertTrue(snapshot.active());
    }
}
