package com.zthcpa.command.persistence;

public final class PostgresRunSql {
    public static final String FIND_BY_ID = """
            SELECT id, pipeline_id, input, status, error, created_at, finished_at
            FROM pipeline_runs
            WHERE id = :runId
            """;

    public static final String COMPARE_AND_SET_STATUS = """
            UPDATE pipeline_runs
            SET status = :nextStatus
            WHERE id = :runId AND status = :expectedStatus
            """;

    public static final String FINISH = """
            UPDATE pipeline_runs
            SET status = :status, error = :error, finished_at = now()
            WHERE id = :runId
            """;

    private PostgresRunSql() {
    }
}
