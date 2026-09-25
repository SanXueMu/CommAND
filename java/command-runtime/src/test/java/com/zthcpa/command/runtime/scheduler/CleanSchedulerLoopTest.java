package com.zthcpa.command.runtime.scheduler;

import com.zthcpa.command.runtime.dispatch.TaskDispatcher;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort.TaskExecution;
import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import com.zthcpa.command.runtime.worker.WorkerRuntime;
import com.zthcpa.command.runtime.worker.WorkerRuntimeException;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanSchedulerLoopTest {
    @Test
    void startsPollsAndStops() throws Exception {
        AtomicInteger polls = new AtomicInteger();
        CountDownLatch firstPoll = new CountDownLatch(1);
        CleanSchedulerLoop loop = new CleanSchedulerLoop(
                scheduler(polls, firstPoll), "worker-a", Duration.ofMillis(10), exception -> {
                    throw new AssertionError(exception);
                }
        );

        loop.start();
        assertTrue(firstPoll.await(1, TimeUnit.SECONDS));
        loop.stop();
        int stoppedAt = polls.get();
        Thread.sleep(40);

        assertEquals(stoppedAt, polls.get());
        loop.close();
    }

    @Test
    void isolatesPollErrorsAndContinues() throws Exception {
        AtomicInteger polls = new AtomicInteger();
        CountDownLatch thirdPoll = new CountDownLatch(1);
        CopyOnWriteArrayList<RuntimeException> errors = new CopyOnWriteArrayList<>();
        CleanScheduler scheduler = new CleanScheduler(dispatcherFor(() -> {
            int current = polls.incrementAndGet();
            if (current == 1) {
                throw new WorkerRuntimeException("temporary");
            }
            if (current == 3) {
                thirdPoll.countDown();
            }
            return false;
        }));
        CleanSchedulerLoop loop = new CleanSchedulerLoop(
                scheduler, "worker-a", Duration.ofMillis(10), errors::add
        );

        loop.start();
        assertTrue(thirdPoll.await(1, TimeUnit.SECONDS));
        loop.stop();

        assertEquals(1, errors.size());
    }

    @Test
    void rejectsInvalidLifecycleConfiguration() {
        CleanScheduler scheduler = new CleanScheduler(new TaskDispatcher(
                new TaskPort(), new Worker()
        ));

        assertThrows(IllegalArgumentException.class, () -> new CleanSchedulerLoop(
                scheduler, "worker-a", Duration.ZERO, exception -> {
                }
        ));
    }

    private static CleanScheduler scheduler(AtomicInteger polls, CountDownLatch firstPoll) {
        return new CleanScheduler(dispatcherFor(() -> {
            polls.incrementAndGet();
            firstPoll.countDown();
            return false;
        }));
    }

    private static TaskDispatcher dispatcherFor(java.util.function.BooleanSupplier poll) {
        return new TaskDispatcher(new TaskPort() {
            @Override
            public TaskExecution claim(String workerId) {
                poll.getAsBoolean();
                return null;
            }
        }, new Worker());
    }

    private static class TaskPort implements TaskExecutionPort {
        @Override
        public TaskExecution claim(String workerId) {
            return null;
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

    private static final class Worker implements WorkerRuntime {
        @Override
        public WorkerJob createJob(String toolId, WorkerJobRequest request) {
            return new WorkerJob("job", "succeeded", Map.of(), null);
        }

        @Override
        public WorkerJob getJob(String jobId) {
            return new WorkerJob(jobId, "succeeded", Map.of(), null);
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
