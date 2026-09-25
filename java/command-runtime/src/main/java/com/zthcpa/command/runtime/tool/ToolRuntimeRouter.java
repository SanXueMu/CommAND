package com.zthcpa.command.runtime.tool;

import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import com.zthcpa.command.runtime.worker.WorkerRuntime;
import com.zthcpa.command.runtime.worker.WorkerRuntimeException;
import com.zthcpa.command.tools.spi.JavaToolRegistry;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** Routes registered Java tools in-process and delegates other tools to an external Worker. */
public final class ToolRuntimeRouter implements WorkerRuntime {
    private final JavaToolRegistry tools;
    private final WorkerRuntime inProcess;
    private final WorkerRuntime external;
    private final Map<String, WorkerRuntime> jobs = new ConcurrentHashMap<>();

    public ToolRuntimeRouter(JavaToolRegistry tools, WorkerRuntime inProcess, WorkerRuntime external) {
        this.tools = tools;
        this.inProcess = inProcess;
        this.external = external;
    }

    @Override
    public WorkerJob createJob(String toolId, WorkerJobRequest request) {
        WorkerRuntime runtime = tools.contains(toolId, 1) ? inProcess : external;
        if (runtime == null) {
            throw new WorkerRuntimeException("No runtime registered for tool: " + toolId);
        }
        WorkerJob job = runtime.createJob(toolId, request);
        jobs.put(job.jobId(), runtime);
        return job;
    }

    @Override
    public WorkerJob getJob(String jobId) {
        return runtime(jobId).getJob(jobId);
    }

    @Override
    public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
        return runtime(jobId).listEvents(jobId, afterSequence);
    }

    @Override
    public void cancelJob(String jobId) {
        runtime(jobId).cancelJob(jobId);
    }

    private WorkerRuntime runtime(String jobId) {
        WorkerRuntime runtime = jobs.get(jobId);
        if (runtime == null) {
            throw new WorkerRuntimeException("Tool runtime job not found: " + jobId);
        }
        return runtime;
    }
}
