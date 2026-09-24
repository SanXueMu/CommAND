package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRunCompletionFailureTest {
    @Test
    void rejectsSuccessAndCancellationAsFailureStatus() {
        var repository = new CleanRunCompletionRepository(
                null, new ObjectMapper()
        );
        assertThrows(IllegalArgumentException.class, () -> repository.failTask(
                "task-1", "worker-1", TaskStatus.SUCCEEDED, Map.of()
        ));
    }
}
