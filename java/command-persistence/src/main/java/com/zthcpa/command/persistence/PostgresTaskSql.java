package com.zthcpa.command.persistence;

public final class PostgresTaskSql {
    public static final String FIND_BY_HANDLE = """
            SELECT handle, tool_id, input, output, status, error,
                   pipeline_run, step_index, attempt, max_attempts
            FROM tasks
            WHERE handle = :handle
            """;

    public static final String CLAIM_NEXT = """
            WITH candidate AS (
                SELECT t.handle
                FROM tasks t
                JOIN tools tl ON tl.id = t.tool_id
                WHERE t.status = 'queued'
                  AND (SELECT count(*) FROM tasks r
                       WHERE r.tool_id = t.tool_id AND r.status = 'running')
                      < (tl.manifest->'resources'->>'concurrency')::int
                ORDER BY t.created_at
                FOR UPDATE OF t SKIP LOCKED
                LIMIT 1
            )
            UPDATE tasks
            SET status = 'running', claimed_by = :workerId,
                started_at = now(), heartbeat_at = now()
            WHERE handle IN (SELECT handle FROM candidate)
            RETURNING handle, tool_id, input, output, status, error,
                      pipeline_run, step_index, attempt, max_attempts
            """;

    public static final String COMPARE_AND_SET_STATUS = """
            UPDATE tasks
            SET status = :nextStatus
            WHERE handle = :handle AND status = :expectedStatus
            """;

    public static final String REQUEUE = """
            UPDATE tasks
            SET status = 'queued', attempt = attempt + 1,
                claimed_by = NULL, started_at = NULL, heartbeat_at = NULL
            WHERE handle = :handle AND status = 'running'
            """;

    private PostgresTaskSql() {
    }
}
