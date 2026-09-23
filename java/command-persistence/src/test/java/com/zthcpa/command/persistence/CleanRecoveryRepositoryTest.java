package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.postgresql.ds.PGSimpleDataSource;

import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;

class CleanRecoveryRepositoryTest {
    @Test
    void rejectsBlankRunId() {
        var repository = new CleanRecoveryRepository(null, new ObjectMapper(), new PGSimpleDataSource());
        assertThrows(IllegalArgumentException.class, () -> repository.recoverInterruptedRun(" "));
    }

    @Test
    void rejectsInvalidStaleRecoveryArguments() {
        var repository = new CleanRecoveryRepository(null, new ObjectMapper(), new PGSimpleDataSource());
        assertThrows(IllegalArgumentException.class, () -> repository.recoverStaleTasks(null, 10));
        assertThrows(IllegalArgumentException.class, () -> repository.recoverStaleTasks(Instant.now(), 0));
    }

}
