package com.zthcpa.command.persistence;

import com.zthcpa.command.run.RunStatus;

import java.util.Optional;

public interface RunRepository {
    Optional<RunRow> findById(String runId);

    boolean compareAndSetStatus(String runId, RunStatus expected, RunStatus next);

    void finish(String runId, RunStatus status, java.util.Map<String, Object> error);
}
