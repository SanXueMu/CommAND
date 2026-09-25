package com.zthcpa.command.runtime.scheduler;

import com.zthcpa.command.runtime.dispatch.TaskDispatcher;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort.TaskExecution;
import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import com.zthcpa.command.runtime.worker.WorkerRuntime;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanSchedulerTest {
    @Test
    void returnsDispatchedWhenDispatcherClaimsTask() {
        CleanScheduler scheduler = new CleanScheduler(new TaskDispatcher(
                new FakeTaskPort(true), new FakeWorker()
        ));

        CleanScheduler.PollResult result = scheduler.pollOnce("worker-a");

        assertEquals("worker-a", result.workerId());
        assertTrue(result.dispatched());
    }

    @Test
    void returnsIdleWhenNoTaskIsAvailable() {
        CleanScheduler scheduler = new CleanScheduler(new TaskDispatcher(
                new FakeTaskPort(false), new FakeWorker()
        ));

        assertFalse(scheduler.pollOnce("worker-a").dispatched());
    }

    @Test
    void rejectsBlankWorkerId() {
        CleanScheduler scheduler = new CleanScheduler(new TaskDispatcher(
                new FakeTaskPort(false), new FakeWorker()
        ));

        assertThrows(IllegalArgumentException.class, () -> scheduler.pollOnce(" "));
    }

    private static final class FakeTaskPort implements TaskExecutionPort {
        private final boolean available;

        private FakeTaskPort(boolean available) {
            this.available = available;
        }

        @Override
        public TaskExecution claim(String workerId) {
            return available ? new TaskExecution("task-1", "tool-1", 1, Map.of(), workerId) : null;
        }

        @Override
        public void recordWorkerEvent(String taskId, WorkerEvent event) {
        }

        @Override
        public void succeed(String taskId, String workerId, Map<String, Object> output) {
        }

        @Override
        public void fail(String taskId, String workerId, Map<String, Object> error) {
        }

        @Override
        public void cancel(String taskId, String workerId, Map<String, Object> detail) {
        }
    }

    private static final class FakeWorker implements WorkerRuntime {
        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            return new WorkerJob("job-1", "queued", null, null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            return new WorkerJob(jobId, "succeeded", Map.of("ok", true), null);
        }

        @Override
        public java.util.List<WorkerEvent> listEvents(String jobId, long afterSequence) {
            return java.util.List.of();
        }

        @Override
        public void cancelJob(String jobId) {
        }
    }
}
