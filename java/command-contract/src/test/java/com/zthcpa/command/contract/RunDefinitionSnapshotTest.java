package com.zthcpa.command.contract;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RunDefinitionSnapshotTest {
    private static final String CHECKSUM = "3e39a652e63fe7c7617ec4c28c310610c15f470d4ef6d09d4a1ea675f9e1ee1c";

    @Test
    void acceptsValidSnapshot() {
        RunDefinitionSnapshot snapshot = new RunDefinitionSnapshot(
                "run-1",
                new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", 1),
                1,
                CHECKSUM,
                Map.of("id", "ocr.extract-document")
        );

        assertEquals("run-1", snapshot.runId());
        assertEquals(DefinitionKind.WORKFLOW, snapshot.key().kind());
    }

    @Test
    void rejectsBlankRunIdAndBadChecksum() {
        DefinitionKey key = new DefinitionKey(DefinitionKind.WORKFLOW, "ocr.extract-document", 1);

        assertThrows(IllegalArgumentException.class, () -> new RunDefinitionSnapshot(
                " ", key, 1, CHECKSUM, Map.of()
        ));
        assertThrows(IllegalArgumentException.class, () -> new RunDefinitionSnapshot(
                "run-1", key, 1, "not-a-checksum", Map.of()
        ));
        assertThrows(IllegalArgumentException.class, () -> new RunDefinitionSnapshot(
                "run-1", key, 0, CHECKSUM, Map.of()
        ));
    }
}
