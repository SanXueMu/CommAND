package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RunLifecycleTest {
    private static final Instant NOW = Instant.parse("2026-09-22T12:00:00Z");
    private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
    private final DefinitionKey workflow = new DefinitionKey(
            DefinitionKind.WORKFLOW, "ocr.extract-document", 1
    );

    @Test
    void transitionsRunAndRecordsTerminalTime() {
        RunLifecycle lifecycle = new RunLifecycle("run-1", workflow, Map.of("file", "a.pdf"), clock);

        assertEquals(RunStatus.RUNNING, lifecycle.snapshot().status());
        assertEquals(RunStatus.PAUSED, lifecycle.pause().status());
        assertEquals(RunStatus.RUNNING, lifecycle.resume().status());
        assertEquals(RunStatus.SUCCEEDED, lifecycle.succeed().status());
        assertEquals(NOW, lifecycle.snapshot().finishedAt());
    }

    @Test
    void rejectsTransitionFromTerminalState() {
        RunLifecycle lifecycle = new RunLifecycle("run-1", workflow, Map.of(), clock);
        lifecycle.cancel();

        assertThrows(InvalidRunTransitionException.class, lifecycle::resume);
    }

    @Test
    void recordsFailureWithoutChangingOriginalInput() {
        RunLifecycle lifecycle = new RunLifecycle("run-1", workflow, Map.of("file", "a.pdf"), clock);
        lifecycle.fail(Map.of("kind", "tool", "message", "failed"));

        assertNotNull(lifecycle.snapshot().error());
        assertEquals("a.pdf", lifecycle.snapshot().input().get("file"));
    }
}
