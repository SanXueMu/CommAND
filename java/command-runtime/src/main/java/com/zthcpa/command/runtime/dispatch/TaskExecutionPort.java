package com.zthcpa.command.runtime.dispatch;

import com.zthcpa.command.runtime.worker.WorkerEvent;

import java.util.Map;

public interface TaskExecutionPort {
    TaskExecution claim(String workerId);

    default boolean heartbeat(String taskId, String workerId) {
        return true;
    }

    default boolean isCancellationRequested(String taskId, String workerId) {
        return false;
    }

    void recordWorkerEvent(String taskId, WorkerEvent event);

    void succeed(String taskId, String workerId, Map<String, Object> output);

    void fail(String taskId, String workerId, Map<String, Object> error);

    void cancel(String taskId, String workerId, Map<String, Object> detail);

    record TaskExecution(
            String taskId,
            String toolId,
            int attempt,
            Map<String, Object> input,
            String workerId
    ) {
    }
}
