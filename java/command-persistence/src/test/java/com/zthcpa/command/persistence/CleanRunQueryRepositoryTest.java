package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRunQueryRepositoryTest {
    @Test
    void validatesListAndEventBounds() {
        var repository = new CleanRunQueryRepository(null, new ObjectMapper());
        assertThrows(IllegalArgumentException.class, () -> repository.list(-1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listEvents("run-1", -1, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.listEvents("run-1", 0, 1001));
    }
}
