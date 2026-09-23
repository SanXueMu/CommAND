package com.zthcpa.command.persistence;

import com.zthcpa.command.run.TaskStatus;

import java.util.Optional;

public interface TaskRepository {
    Optional<TaskRow> findByHandle(String handle);

    Optional<TaskRow> claimNext(String workerId);

    boolean compareAndSetStatus(String handle, TaskStatus expected, TaskStatus next);

    void requeue(String handle);

    void finish(String handle, TaskStatus status, java.util.Map<String, Object> output,
                java.util.Map<String, Object> error);
}
