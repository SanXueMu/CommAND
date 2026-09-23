package com.zthcpa.command.persistence;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanEventRepositoryTest {
    @Test
    void queriesOnlyNewCleanEventTables() {
        assertTrue(CleanEventSql.LIST_RUN.contains("command_runtime.run_events"));
        assertTrue(CleanEventSql.LIST_TASK.contains("command_runtime.task_events"));
        assertTrue(CleanEventSql.LIST_RUN.contains("id > :afterId"));
    }

    @Test
    void validatesIncrementalQueryBounds() {
        var repository = new JdbcCleanEventRepository(null, null);
        assertThrows(IllegalArgumentException.class, () -> repository.listRunEvents("run-1", -1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listTaskEvents("task-1", 0, 1001));
    }
}
