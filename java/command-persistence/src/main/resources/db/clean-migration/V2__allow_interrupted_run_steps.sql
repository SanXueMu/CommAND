ALTER TABLE command_runtime.run_steps
    DROP CONSTRAINT run_steps_status_check;

ALTER TABLE command_runtime.run_steps
    ADD CONSTRAINT run_steps_status_check CHECK (status IN (
        'pending', 'queued', 'running', 'paused', 'succeeded', 'failed',
        'cancelled', 'interrupted', 'skipped'
    ));
