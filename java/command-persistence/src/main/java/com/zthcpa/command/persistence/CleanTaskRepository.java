package com.zthcpa.command.persistence;

import com.zthcpa.command.run.TaskStatus;

import java.util.Map;
import java.util.Optional;

public interface CleanTaskRepository {
    Optional<CleanTaskRow> claimNext(String workerId);

    boolean isCancellationRequested(String taskId, String workerId);

    boolean heartbeat(String taskId, String workerId);

    boolean finish(String taskId, String workerId, TaskStatus status,
                   Map<String, Object> output, Map<String, Object> error);

    boolean requeue(String taskId, String workerId);
}
