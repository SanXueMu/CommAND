package com.zthcpa.command.runtime.dispatch;

import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerRuntimeException;

import com.zthcpa.command.persistence.event.CleanEventRepository;
import com.zthcpa.command.persistence.task.CleanRunCompletionRepository;
import com.zthcpa.command.persistence.task.CleanTaskRepository;
import com.zthcpa.command.persistence.task.CleanTaskRow;
import com.zthcpa.command.run.TaskStatus;

import java.util.Map;

public final class PersistentTaskExecutionPort implements TaskExecutionPort {
    private final CleanTaskRepository tasks;
    private final CleanEventRepository events;
    private final CleanRunCompletionRepository completion;

    public PersistentTaskExecutionPort(
            CleanTaskRepository tasks,
            CleanEventRepository events,
            CleanRunCompletionRepository completion
    ) {
        this.tasks = tasks;
        this.events = events;
        this.completion = completion;
    }

    @Override
    public TaskExecution claim(String workerId) {
        return tasks.claimNext(workerId).map(this::toExecution).orElse(null);
    }

    @Override
    public boolean isCancellationRequested(String taskId, String workerId) {
        return tasks.isCancellationRequested(taskId, workerId);
    }

    @Override
    public void recordWorkerEvent(String taskId, WorkerEvent event) {
        events.appendTaskEvent(taskId, "worker." + event.type(), event.data());
    }

    @Override
    public void succeed(String taskId, String workerId, Map<String, Object> output) {
        requireCompletion(completion.completeTask(taskId, workerId, TaskStatus.SUCCEEDED, output, null), taskId);
    }

    @Override
    public void fail(String taskId, String workerId, Map<String, Object> error) {
        requireCompletion(completion.failTask(taskId, workerId, TaskStatus.FAILED, error), taskId);
    }

    @Override
    public void cancel(String taskId, String workerId, Map<String, Object> detail) {
        requireCompletion(completion.stopTask(taskId, workerId, TaskStatus.CANCELLED, detail), taskId);
    }

    private TaskExecution toExecution(CleanTaskRow task) {
        return new TaskExecution(task.id(), task.toolId(), task.attempt(), task.input(), task.workerId());
    }

    private static void requireCompletion(boolean completed, String taskId) {
        if (!completed) {
            throw new WorkerRuntimeException("Task was no longer claimable: " + taskId);
        }
    }
}
