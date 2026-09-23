package com.zthcpa.command.persistence;

public final class CleanTaskSql {
    public static final String CLAIM_NEXT = """
            WITH candidate AS (
                SELECT t.id, t.step_id
                FROM command_runtime.task_executions t
                JOIN command_runtime.run_steps s ON s.id = t.step_id
                WHERE t.status = 'queued' AND s.status = 'queued'
                ORDER BY t.created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            , claimed_step AS (
                UPDATE command_runtime.run_steps s
                SET status = 'running', started_at = COALESCE(s.started_at, now())
                FROM candidate
                WHERE s.id = candidate.step_id
                RETURNING s.id
            )
            UPDATE command_runtime.task_executions t
            SET status = 'running', worker_id = :workerId,
                started_at = COALESCE(t.started_at, now()), heartbeat_at = now()
            FROM candidate
            JOIN claimed_step ON claimed_step.id = candidate.step_id
            WHERE t.id = candidate.id
            RETURNING t.id, t.step_id, (SELECT step_key FROM command_runtime.run_steps WHERE id = t.step_id) AS tool_id,
                      t.attempt, t.max_attempts, t.worker_id,
                      t.input, t.output, t.error, t.status
            """;

    public static final String HEARTBEAT = """
            UPDATE command_runtime.task_executions
            SET heartbeat_at = now()
            WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
            """;

    public static final String FINISH = """
            UPDATE command_runtime.task_executions
            SET status = :status, output = CAST(:output AS jsonb),
                error = CAST(:error AS jsonb), finished_at = now()
            WHERE id = :taskId AND worker_id = :workerId AND status = 'running'
            """;

    public static final String REQUEUE = """
            UPDATE command_runtime.task_executions
            SET status = 'queued', attempt = attempt + 1,
                worker_id = NULL, heartbeat_at = NULL, started_at = NULL
            WHERE id = :taskId AND worker_id = :workerId
              AND status = 'running' AND attempt < max_attempts
            """;

    private CleanTaskSql() {
    }
}
