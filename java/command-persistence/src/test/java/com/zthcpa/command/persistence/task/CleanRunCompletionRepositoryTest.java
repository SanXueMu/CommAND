package com.zthcpa.command.persistence.task;

import com.zthcpa.command.persistence.task.CleanRunCompletionRepository;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRunCompletionRepositoryTest {
    @Test
    void completionRejectsNonTerminalStatusBeforeTransaction() {
        var repository = new CleanRunCompletionRepository(null, new ObjectMapper());
        assertThrows(IllegalArgumentException.class, () -> repository.completeTask(
                "task-1", "worker-1", TaskStatus.RUNNING, Map.of(), null
        ));
    }
}
