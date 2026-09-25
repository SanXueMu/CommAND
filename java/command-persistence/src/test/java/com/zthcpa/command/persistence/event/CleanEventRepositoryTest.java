package com.zthcpa.command.persistence.event;

import com.zthcpa.command.persistence.event.HibernateCleanEventRepository;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanEventRepositoryTest {
    @Test
    void validatesIncrementalQueryBounds() {
        var repository = new HibernateCleanEventRepository(null);
        assertThrows(IllegalArgumentException.class, () -> repository.listRunEvents("run-1", -1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listTaskEvents("task-1", 0, 1001));
    }
}
