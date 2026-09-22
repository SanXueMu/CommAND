package com.zthcpa.command.persistence;

import com.zthcpa.command.run.RunStatus;
import com.zthcpa.command.run.TaskStatus;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StatusValueMapperTest {
    @Test
    void mapsRunStatusesToExistingDatabaseValues() {
        assertEquals("running", StatusValueMapper.toDatabase(RunStatus.RUNNING));
        assertEquals("failed_review", StatusValueMapper.toDatabase(RunStatus.FAILED_REVIEW));
        assertEquals(RunStatus.PAUSED, StatusValueMapper.toRunStatus("paused"));
    }

    @Test
    void mapsTaskStatusesToExistingDatabaseValues() {
        assertEquals("queued", StatusValueMapper.toDatabase(TaskStatus.QUEUED));
        assertEquals("failed_review", StatusValueMapper.toDatabase(TaskStatus.FAILED_REVIEW));
        assertEquals(TaskStatus.INTERRUPTED, StatusValueMapper.toTaskStatus("interrupted"));
    }

    @Test
    void rejectsUnknownDatabaseValues() {
        assertThrows(IllegalArgumentException.class, () -> StatusValueMapper.toRunStatus("unknown"));
        assertThrows(IllegalArgumentException.class, () -> StatusValueMapper.toTaskStatus("unknown"));
    }
}
