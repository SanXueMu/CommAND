package com.zthcpa.command.persistence;

public final class CleanEventSql {
    public static final String INSERT_RUN = """
            INSERT INTO command_runtime.run_events (run_id, step_id, kind, actor, detail)
            VALUES (:runId, :stepId, :kind, :actor, CAST(:detail AS jsonb))
            RETURNING id
            """;

    public static final String INSERT_TASK = """
            INSERT INTO command_runtime.task_events (task_id, kind, detail)
            VALUES (:taskId, :kind, CAST(:detail AS jsonb))
            RETURNING id
            """;

    public static final String LIST_RUN = """
            SELECT id, run_id, step_id, kind, actor, detail, created_at
            FROM command_runtime.run_events
            WHERE run_id = :runId AND id > :afterId
            ORDER BY id
            LIMIT :limit
            """;

    public static final String LIST_TASK = """
            SELECT id, task_id, kind, detail, created_at
            FROM command_runtime.task_events
            WHERE task_id = :taskId AND id > :afterId
            ORDER BY id
            LIMIT :limit
            """;

    private CleanEventSql() {
    }
}
