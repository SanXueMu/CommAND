package com.zthcpa.command.runtime;

import com.zthcpa.command.api.RecoveryStatusPort;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecoveryStatusConfigurationTest {
    @Test
    void enabledStatusReadsTheLoopMetrics() {
        RecoveryMetrics metrics = new RecoveryMetrics();
        CleanRecoveryLoop loop = new CleanRecoveryLoop(
                new CleanRecoveryPoller(
                        (staleBefore, limit) -> 0,
                        Clock.fixed(Instant.parse("2026-09-24T00:00:00Z"), ZoneOffset.UTC),
                        Duration.ofMinutes(5),
                        50
                ),
                Duration.ofSeconds(1),
                exception -> { },
                metrics
        );
        metrics.recordPoll(Instant.parse("2026-09-24T01:00:00Z"), 3);

        RecoveryStatusPort.Status status = new RecoveryStatusConfiguration()
                .enabledRecoveryStatus(loop)
                .status();

        assertTrue(status.enabled());
        assertFalse(status.active());
        assertEquals(1, status.polls());
        assertEquals(3, status.recovered());
        assertEquals(3, status.lastRecovered());
        assertEquals(Instant.parse("2026-09-24T01:00:00Z"), status.lastPollAt());
        loop.close();
    }
}
