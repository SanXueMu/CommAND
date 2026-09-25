package com.zthcpa.command.runtime.worker;

import java.util.List;

public interface WorkerRuntime {
    WorkerJob createJob(String toolId, WorkerJobRequest request);

    WorkerJob getJob(String jobId);

    List<WorkerEvent> listEvents(String jobId, long afterSequence);

    void cancelJob(String jobId);
}
