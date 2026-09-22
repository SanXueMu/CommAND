package com.zthcpa.command.run;

import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.ToolKey;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class SnapshotTest {
    @Test
    void rejectsInvalidTaskAttemptRange() {
        assertThrows(IllegalArgumentException.class, () -> new TaskSnapshot(
                "task-1",
                new ToolKey("ocr.page.extract", 1),
                TaskStatus.QUEUED,
                Map.of(),
                null,
                null,
                2,
                1
        ));
    }

    @Test
    void rejectsBlankRunId() {
        assertThrows(IllegalArgumentException.class, () -> new RunSnapshot(
                "",
                new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", 1),
                RunStatus.RUNNING,
                Map.of(),
                null,
                Instant.now(),
                null
        ));
    }
}
