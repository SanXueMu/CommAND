package com.zthcpa.command.runtime;

import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.JavaToolRegistry;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InProcessToolRuntimeTest {
    @Test
    void runsJavaToolAndRelaysProgressEvents() throws Exception {
        JavaTool tool = new JavaTool() {
            @Override public String id() { return "llm.chat.complete"; }
            @Override public int version() { return 1; }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                progress.emit(Map.of("phase", "completed"));
                return Map.of("content", "completed");
            }
        };
        try (InProcessToolRuntime runtime = new InProcessToolRuntime(new JavaToolRegistry(List.of(tool)))) {
            WorkerJob created = runtime.createJob("llm.chat.complete", new WorkerJobRequest(
                    "llm.chat.complete", "task-1", 1, Map.of("messages", List.of())
            ));

            WorkerJob completed = await(runtime, created.jobId(), "succeeded");
            assertEquals(Map.of("content", "completed"), completed.output());
            assertTrue(runtime.listEvents(created.jobId(), 0).stream()
                    .anyMatch(event -> "progress".equals(event.type())));
        }
    }

    @Test
    void recordsJavaToolFailureAsStructuredJobFailure() throws Exception {
        JavaTool tool = new JavaTool() {
            @Override public String id() { return "llm.chat.complete"; }
            @Override public int version() { return 1; }
            @Override public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
                throw new IllegalStateException("model unavailable");
            }
        };
        try (InProcessToolRuntime runtime = new InProcessToolRuntime(new JavaToolRegistry(List.of(tool)))) {
            WorkerJob created = runtime.createJob("llm.chat.complete", new WorkerJobRequest(
                    "llm.chat.complete", "task-2", 1, Map.of()
            ));

            WorkerJob failed = await(runtime, created.jobId(), "failed");
            assertEquals("JAVA_TOOL_ERROR", failed.error().get("code"));
        }
    }

    private WorkerJob await(InProcessToolRuntime runtime, String jobId, String status) throws InterruptedException {
        long deadline = System.nanoTime() + Duration.ofSeconds(2).toNanos();
        WorkerJob job;
        do {
            job = runtime.getJob(jobId);
            if (status.equals(job.status())) {
                return job;
            }
            Thread.sleep(10);
        } while (System.nanoTime() < deadline);
        throw new AssertionError("Job did not reach " + status + ": " + job.status());
    }
}
