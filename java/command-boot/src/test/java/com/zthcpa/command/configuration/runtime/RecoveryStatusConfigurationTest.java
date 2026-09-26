package com.zthcpa.command.configuration.runtime;

import com.zthcpa.command.api.port.RecoveryStatusPort;
import com.zthcpa.command.runtime.recovery.CleanRecoveryLoop;
import com.zthcpa.command.runtime.recovery.CleanRecoveryPoller;
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
    void enabledStatusReadsTheLoopMetrics() throws Exception {
        CleanRecoveryLoop loop = new CleanRecoveryLoop(
                new CleanRecoveryPoller(
                        (staleBefore, limit) -> 3,
                        Clock.fixed(Instant.parse("2026-09-24T00:00:00Z"), ZoneOffset.UTC),
                        Duration.ofMinutes(5),
                        50
                ),
                Duration.ofSeconds(1),
                exception -> { }
        );
        loop.start();

        RecoveryStatusConfiguration configuration = new RecoveryStatusConfiguration();
        RecoveryStatusPort.Status status = configuration.enabledRecoveryStatus(loop).status();
        long deadline = System.nanoTime() + Duration.ofSeconds(1).toNanos();
        while (status.polls() == 0 && System.nanoTime() < deadline) {
            Thread.sleep(10);
            status = configuration.enabledRecoveryStatus(loop).status();
        }
        loop.stop();

        assertTrue(status.enabled());
        assertTrue(status.active());
        assertEquals(1, status.polls());
        assertEquals(3, status.recovered());
        assertEquals(3, status.lastRecovered());
        assertTrue(status.lastPollAt() != null);
        loop.close();
    }
}
