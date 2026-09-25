package com.zthcpa.command.runtime.tool;

import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import com.zthcpa.command.runtime.worker.WorkerRuntime;
import com.zthcpa.command.runtime.worker.WorkerRuntimeException;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.JavaToolRegistry;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ToolRuntimeRouterTest {
    @Test
    void routesRegisteredJavaToolsInProcessAndOtherToolsExternally() {
        JavaTool tool = new JavaTool() {
            @Override public String id() { return "llm.chat.complete"; }
            @Override public int version() { return 1; }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                return Map.of();
            }
        };
        var registry = new JavaToolRegistry(List.of(tool));
        var inProcess = new FakeRuntime("java-job");
        var external = new FakeRuntime("http-job");
        var router = new ToolRuntimeRouter(registry, inProcess, external);

        WorkerJob javaJob = router.createJob("llm.chat.complete", request("llm.chat.complete"));
        WorkerJob httpJob = router.createJob("file.inspect", request("file.inspect"));

        assertEquals("java-job", javaJob.jobId());
        assertEquals("http-job", httpJob.jobId());
        assertEquals("java-job", router.getJob(javaJob.jobId()).jobId());
        assertEquals("http-job", router.getJob(httpJob.jobId()).jobId());
        router.cancelJob(javaJob.jobId());
        router.cancelJob(httpJob.jobId());
        assertEquals(1, inProcess.cancellations);
        assertEquals(1, external.cancellations);
    }

    @Test
    void rejectsUnknownToolWhenNoExternalRuntimeIsConfigured() {
        var router = new ToolRuntimeRouter(new JavaToolRegistry(List.of()), new FakeRuntime("java-job"), null);

        assertThrows(
                WorkerRuntimeException.class,
                () -> router.createJob("file.inspect", request("file.inspect"))
        );
    }

    private WorkerJobRequest request(String toolId) {
        return new WorkerJobRequest(toolId, "task-1", 1, Map.of());
    }

    private static final class FakeRuntime implements WorkerRuntime {
        private final String jobId;
        private int cancellations;

        private FakeRuntime(String jobId) {
            this.jobId = jobId;
        }

        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            return new WorkerJob(jobId, "running", null, null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            return new WorkerJob(jobId, "running", null, null);
        }

        @Override
        public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
            return List.of();
        }

        @Override
        public void cancelJob(String jobId) {
            cancellations++;
        }
    }
}
