package com.zthcpa.command.runtime;

import java.util.List;

public final class TaskDispatcher {
    private final TaskExecutionPort tasks;
    private final WorkerRuntime worker;

    public TaskDispatcher(TaskExecutionPort tasks, WorkerRuntime worker) {
        this.tasks = tasks;
        this.worker = worker;
    }

    public boolean dispatchNext(String workerId) {
        TaskExecutionPort.TaskExecution task = tasks.claim(workerId);
        if (task == null) {
            return false;
        }
        WorkerJob job;
        try {
            job = worker.createJob(task.toolId(), new WorkerJobRequest(
                    task.toolId(), task.taskId(), task.attempt(), task.input()
            ));
            relayEvents(task.taskId(), job.jobId(), 0);
            WorkerJob finalJob = worker.getJob(job.jobId());
            switch (finalJob.status()) {
                case "succeeded" -> tasks.succeed(task.taskId(), workerId, finalJob.output());
                case "cancelled" -> tasks.cancel(task.taskId(), workerId, finalJob.error());
                case "failed", "failed_review" -> tasks.fail(task.taskId(), workerId, finalJob.error());
                default -> throw new WorkerRuntimeException("Worker job did not reach terminal state: " + finalJob.status());
            }
            return true;
        } catch (WorkerRuntimeException exception) {
            tasks.fail(task.taskId(), workerId, java.util.Map.of(
                    "code", "WORKER_RUNTIME_ERROR", "message", exception.getMessage()
            ));
            throw exception;
        }
    }

    private void relayEvents(String taskId, String jobId, long afterSequence) {
        List<WorkerEvent> events = worker.listEvents(jobId, afterSequence);
        for (WorkerEvent event : events) {
            tasks.recordWorkerEvent(taskId, event);
        }
    }
}
