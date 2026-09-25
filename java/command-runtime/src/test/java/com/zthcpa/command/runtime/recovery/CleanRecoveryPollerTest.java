package com.zthcpa.command.runtime.recovery;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRecoveryPollerTest {
    @Test
    void passesCutoffAndBatchSizeToRecoveryPort() {
        Instant now = Instant.parse("2026-09-23T12:00:00Z");
        AtomicReference<Instant> cutoff = new AtomicReference<>();
        AtomicInteger limit = new AtomicInteger();
        var poller = new CleanRecoveryPoller(
                (staleBefore, batchSize) -> {
                    cutoff.set(staleBefore);
                    limit.set(batchSize);
                    return 3;
                },
                Clock.fixed(now, ZoneOffset.UTC),
                Duration.ofMinutes(5),
                20
        );

        assertEquals(3, poller.pollOnce());
        assertEquals(now.minus(Duration.ofMinutes(5)), cutoff.get());
        assertEquals(20, limit.get());
    }

    @Test
    void rejectsInvalidRecoveryBounds() {
        var port = (StaleTaskRecoveryPort) (staleBefore, limit) -> 0;
        assertThrows(IllegalArgumentException.class, () -> new CleanRecoveryPoller(
                port, Clock.systemUTC(), Duration.ZERO, 1));
        assertThrows(IllegalArgumentException.class, () -> new CleanRecoveryPoller(
                port, Clock.systemUTC(), Duration.ofSeconds(1), 0));
        assertThrows(IllegalArgumentException.class, () -> new CleanRecoveryPoller(
                port, Clock.systemUTC(), Duration.ofSeconds(1), 1001));
    }
}
