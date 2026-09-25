package com.zthcpa.command.persistence.run;

import com.zthcpa.command.persistence.run.CleanRunQueryRepository;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRunQueryRepositoryTest {
    @Test
    void validatesListAndEventBounds() {
        var repository = new CleanRunQueryRepository((EntityManager) null);
        assertThrows(IllegalArgumentException.class, () -> repository.list(-1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listEvents("run-1", -1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listEvents("run-1", 0, 1001));
    }
}
