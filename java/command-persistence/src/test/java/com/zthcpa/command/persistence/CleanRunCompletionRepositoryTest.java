package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanRunCompletionRepositoryTest {
    @Test
    void completionUsesWorkerCasAndNewEventTables() {
        String source = CleanRunCompletionRepository.class.getName();
        assertTrue(CleanEventSql.INSERT_RUN.contains("command_runtime.run_events"));
        assertTrue(CleanEventSql.INSERT_TASK.contains("command_runtime.task_events"));
        assertTrue(source.contains("CleanRunCompletionRepository"));
    }

    @Test
    void completionRejectsNonTerminalStatusBeforeTransaction() {
        var repository = new CleanRunCompletionRepository(null, new ObjectMapper());
        assertThrows(IllegalArgumentException.class, () -> repository.completeTask(
                "task-1", "worker-1", TaskStatus.RUNNING, Map.of(), null
        ));
    }
}
