package com.zthcpa.command.runtime.tool;

import com.zthcpa.command.catalog.InMemoryToolCatalog;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.RuntimeKind;
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
            @Override public ToolKey key() { return new ToolKey("llm.chat.complete", 1); }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                return Map.of();
            }
        };
        var registry = new JavaToolRegistry(List.of(tool));
        var inProcess = new FakeRuntime("java-job");
        var external = new FakeRuntime("http-job");
        var router = new ToolRuntimeRouter(registry, catalog(
                descriptor("llm.chat.complete", 1, RuntimeKind.INPROC),
                descriptor("file.inspect", 1, RuntimeKind.HTTP)
        ), inProcess, external);

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
        var router = new ToolRuntimeRouter(new JavaToolRegistry(List.of()), catalog(), new FakeRuntime("java-job"), null);

        assertThrows(
                WorkerRuntimeException.class,
                () -> router.createJob("file.inspect", request("file.inspect"))
        );
    }

    @Test
    void routesTheRequestedToolVersionWithoutFallingBackToVersionOne() {
        JavaTool tool = new JavaTool() {
            @Override public ToolKey key() { return new ToolKey("llm.chat.complete", 2); }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                return Map.of();
            }
        };
        var inProcess = new FakeRuntime("java-v2-job");
        var external = new FakeRuntime("http-job");
        var router = new ToolRuntimeRouter(new JavaToolRegistry(List.of(tool)), catalog(
                descriptor("llm.chat.complete", 2, RuntimeKind.INPROC)
        ), inProcess, external);

        WorkerJob job = router.createJob("llm.chat.complete", request("llm.chat.complete", 2));

        assertEquals("java-v2-job", job.jobId());
        assertEquals(1, inProcess.createdJobs);
        assertEquals(0, external.createdJobs);
    }

    private WorkerJobRequest request(String toolId) {
        return request(toolId, 1);
    }

    private WorkerJobRequest request(String toolId, int version) {
        return new WorkerJobRequest(toolId, version, "task-1", 1, Map.of());
    }

    private static InMemoryToolCatalog catalog(ToolDescriptor... descriptors) {
        return new InMemoryToolCatalog(List.of(descriptors));
    }

    private static ToolDescriptor descriptor(String id, int version, RuntimeKind runtime) {
        return new ToolDescriptor(new ToolKey(id, version), runtime, "active", Map.of());
    }

    private static final class FakeRuntime implements WorkerRuntime {
        private final String jobId;
        private int cancellations;
        private int createdJobs;

        private FakeRuntime(String jobId) {
            this.jobId = jobId;
        }

        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            createdJobs++;
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
