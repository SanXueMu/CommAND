package com.zthcpa.command.persistence;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class PostgresSqlTest {
    @Test
    void claimPreservesConcurrentSkipLockedSemantics() {
        assertTrue(PostgresTaskSql.CLAIM_NEXT.contains("FOR UPDATE OF t SKIP LOCKED"));
        assertTrue(PostgresTaskSql.CLAIM_NEXT.contains("status = 'queued'"));
        assertTrue(PostgresTaskSql.CLAIM_NEXT.contains("status = 'running'"));
    }

    @Test
    void statusUpdatesAreCompareAndSetOperations() {
        assertTrue(PostgresRunSql.COMPARE_AND_SET_STATUS.contains("status = :expectedStatus"));
        assertTrue(PostgresTaskSql.COMPARE_AND_SET_STATUS.contains("status = :expectedStatus"));
    }

    @Test
    void requeuePreservesExistingAttemptIncrementRule() {
        assertTrue(PostgresTaskSql.REQUEUE.contains("attempt = attempt + 1"));
        assertTrue(PostgresTaskSql.REQUEUE.contains("status = 'running'"));
    }
}
