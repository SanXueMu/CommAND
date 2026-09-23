package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.postgresql.ds.PGSimpleDataSource;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanRecoveryRepositoryTest {
    @Test
    void rejectsBlankRunId() {
        var repository = new CleanRecoveryRepository(null, new ObjectMapper(), new PGSimpleDataSource());
        assertThrows(IllegalArgumentException.class, () -> repository.recoverInterruptedRun(" "));
    }

}
