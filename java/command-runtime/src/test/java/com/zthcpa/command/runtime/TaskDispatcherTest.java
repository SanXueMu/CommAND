package com.zthcpa.command.runtime;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskDispatcherTest {
    @Test
    void dispatchesSuccessfulJobAndRelaysEvents() {
        FakeTasks tasks = new FakeTasks();
        FakeWorker worker = new FakeWorker("succeeded");
        assertTrue(new TaskDispatcher(tasks, worker).dispatchNext("worker-a"));
        assertEquals(List.of("claim", "event:progress", "success"), tasks.actions);
        assertEquals("task-1", worker.request.taskId());
    }

    @Test
    void dispatchesFailedAndCancelledJobsToSeparatePorts() {
        FakeTasks failedTasks = new FakeTasks();
        assertTrue(new TaskDispatcher(failedTasks, new FakeWorker("failed")).dispatchNext("worker-a"));
        assertEquals(List.of("claim", "event:progress", "fail"), failedTasks.actions);

        FakeTasks cancelledTasks = new FakeTasks();
        assertTrue(new TaskDispatcher(cancelledTasks, new FakeWorker("cancelled")).dispatchNext("worker-a"));
        assertEquals(List.of("claim", "event:progress", "cancel"), cancelledTasks.actions);
    }

    @Test
    void recordsWorkerRuntimeErrorAsFailureAndRethrows() {
        FakeTasks tasks = new FakeTasks();
        assertThrows(WorkerRuntimeException.class,
                () -> new TaskDispatcher(tasks, new FailingWorker()).dispatchNext("worker-a"));
        assertEquals(List.of("claim", "fail"), tasks.actions);
    }

    @Test
    void returnsFalseWhenNoTaskIsAvailable() {
        FakeTasks tasks = new FakeTasks();
        tasks.task = null;
        assertFalse(new TaskDispatcher(tasks, new FakeWorker("succeeded")).dispatchNext("worker-a"));
        assertEquals(List.of("claim"), tasks.actions);
    }

    @Test
    void pollsLongJobAndRelaysEachEventOnlyOnce() {
        FakeTasks tasks = new FakeTasks();
        LongRunningWorker worker = new LongRunningWorker();
        TaskDispatcher dispatcher = new TaskDispatcher(
                tasks,
                worker,
                Duration.ofMillis(1),
                Duration.ofSeconds(1),
                millis -> { },
                new AtomicInteger()::incrementAndGet
        );

        assertTrue(dispatcher.dispatchNext("worker-a"));
        assertEquals(List.of("claim", "event:progress", "event:progress", "success"), tasks.actions);
        assertEquals(List.of(0L, 1L, 2L, 2L), worker.eventCursors);
    }

    private static final class FakeTasks implements TaskExecutionPort {
        private TaskExecution task = new TaskExecution("task-1", "text.llm.translate", 1,
                Map.of("text", "hello"), null);
        private final List<String> actions = new ArrayList<>();

        @Override
        public TaskExecution claim(String workerId) {
            actions.add("claim");
            if (task != null) {
                task = new TaskExecution(task.taskId(), task.toolId(), task.attempt(), task.input(), workerId);
            }
            return task;
        }

        @Override
        public void recordWorkerEvent(String taskId, WorkerEvent event) {
            actions.add("event:" + event.type());
        }

        @Override
        public void succeed(String taskId, String workerId, Map<String, Object> output) {
            actions.add("success");
        }

        @Override
        public void fail(String taskId, String workerId, Map<String, Object> error) {
            actions.add("fail");
        }

        @Override
        public void cancel(String taskId, String workerId, Map<String, Object> detail) {
            actions.add("cancel");
        }
    }

    private static class FakeWorker implements WorkerRuntime {
        private final String status;
        private WorkerJobRequest request;

        private FakeWorker(String status) {
            this.status = status;
        }

        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            this.request = request;
            return new WorkerJob("job-1", "queued", null, null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            return new WorkerJob(jobId, status, Map.of("translated", "你好"), Map.of("code", status));
        }

        @Override
        public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
            return List.of(new WorkerEvent(1, "progress", Map.of("percent", 100)));
        }

        @Override
        public void cancelJob(String jobId) {
        }
    }

    private static final class FailingWorker extends FakeWorker {
        private FailingWorker() {
            super("failed");
        }

        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            throw new WorkerRuntimeException("worker unavailable");
        }
    }

    private static final class LongRunningWorker implements WorkerRuntime {
        private final List<Long> eventCursors = new ArrayList<>();
        private int reads;

        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            return new WorkerJob("job-1", "queued", null, null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            reads++;
            return new WorkerJob(jobId, reads < 3 ? "running" : "succeeded", Map.of("ok", true), null);
        }

        @Override
        public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
            eventCursors.add(afterSequence);
            if (afterSequence == 0) {
                return List.of(new WorkerEvent(1, "progress", Map.of("percent", 10)));
            }
            if (afterSequence == 1) {
                return List.of(
                        new WorkerEvent(1, "progress", Map.of("percent", 10)),
                        new WorkerEvent(2, "progress", Map.of("percent", 100))
                );
            }
            return List.of();
        }

        @Override
        public void cancelJob(String jobId) {
        }
    }
}
