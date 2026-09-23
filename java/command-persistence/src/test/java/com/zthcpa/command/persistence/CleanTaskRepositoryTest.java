package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanTaskRepositoryTest {
    @Test
    void claimUsesCleanSchemaAndSkipLocked() {
        assertTrue(CleanTaskSql.CLAIM_NEXT.contains("command_runtime.task_executions"));
        assertTrue(CleanTaskSql.CLAIM_NEXT.contains("SKIP LOCKED"));
    }

    @Test
    void finishRejectsNonTerminalStatusBeforeJdbc() {
        var repository = new JdbcCleanTaskRepository(null, new ObjectMapper());

        assertThrows(IllegalArgumentException.class, () -> repository.finish(
                "task-1", "worker-1", TaskStatus.RUNNING, Map.of(), null
        ));
    }
}
