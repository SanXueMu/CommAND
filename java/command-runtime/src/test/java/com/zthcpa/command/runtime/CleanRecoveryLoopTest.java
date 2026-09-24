package com.zthcpa.command.runtime;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanRecoveryLoopTest {
    @Test
    void pollsUntilStopped() throws Exception {
        AtomicInteger polls = new AtomicInteger();
        CountDownLatch thirdPoll = new CountDownLatch(3);
        CleanRecoveryLoop loop = loop(() -> {
            polls.incrementAndGet();
            thirdPoll.countDown();
            return 0;
        }, Duration.ofMillis(10), exception -> {
            throw new AssertionError(exception);
        });

        loop.start();
        assertTrue(thirdPoll.await(1, TimeUnit.SECONDS));
        loop.stop();
        int stoppedAt = polls.get();
        Thread.sleep(40);

        assertFalse(loop.isRunning());
        assertEquals(stoppedAt, polls.get());
        loop.close();
    }

    @Test
    void isolatesPollErrorsAndContinues() throws Exception {
        AtomicInteger polls = new AtomicInteger();
        CountDownLatch thirdPoll = new CountDownLatch(1);
        CopyOnWriteArrayList<RuntimeException> errors = new CopyOnWriteArrayList<>();
        CleanRecoveryLoop loop = loop(() -> {
            int current = polls.incrementAndGet();
            if (current == 1) {
                throw new IllegalStateException("temporary");
            }
            if (current == 3) {
                thirdPoll.countDown();
            }
            return 0;
        }, Duration.ofMillis(10), errors::add);

        loop.start();
        assertTrue(thirdPoll.await(1, TimeUnit.SECONDS));
        loop.stop();

        assertEquals(1, errors.size());
    }

    @Test
    void rejectsInvalidIntervalAndRepeatedStart() throws Exception {
        CleanRecoveryLoop loop = loop(() -> 0, Duration.ofMillis(10), exception -> {
            throw new AssertionError(exception);
        });
        assertThrows(IllegalArgumentException.class, () -> loop(
                () -> 0, Duration.ZERO, exception -> { }
        ));

        loop.start();
        assertThrows(IllegalStateException.class, loop::start);
        loop.stop();
        loop.close();
    }

    @Test
    void canStopImmediatelyAfterStart() {
        CleanRecoveryLoop loop = loop(() -> 0, Duration.ofSeconds(1), exception -> {
            throw new AssertionError(exception);
        });

        loop.start();
        loop.stop();

        assertFalse(loop.isRunning());
        loop.close();
    }

    private static CleanRecoveryLoop loop(
            java.util.function.IntSupplier recovery,
            Duration interval,
            java.util.function.Consumer<RuntimeException> errorHandler
    ) {
        return new CleanRecoveryLoop(
                new CleanRecoveryPoller(
                        (staleBefore, limit) -> recovery.getAsInt(),
                        Clock.fixed(Instant.parse("2026-09-24T00:00:00Z"), ZoneOffset.UTC),
                        Duration.ofMinutes(5),
                        50
                ),
                interval,
                errorHandler
        );
    }
}
