package com.zthcpa.command.runtime.scheduler;

import com.sun.net.httpserver.HttpServer;
import com.zthcpa.command.runtime.dispatch.TaskDispatcher;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort;
import com.zthcpa.command.runtime.dispatch.TaskExecutionPort.TaskExecution;
import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerHealthChecker;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import com.zthcpa.command.runtime.worker.WorkerRuntime;
import com.zthcpa.command.runtime.worker.WorkerRuntimeException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerActivationTest {
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void verifiesHealthBeforeStartingLoop() throws Exception {
        CountDownLatch poll = new CountDownLatch(1);
        server = start(200);
        SchedulerActivation activation = new SchedulerActivation(
                healthChecker()::verify, loop(poll)
        );

        activation.activate();

        assertTrue(poll.await(1, TimeUnit.SECONDS));
        assertTrue(activation.isActive());
        activation.close();
    }

    @Test
    void remainsInactiveWhenHealthFails() throws IOException {
        server = start(503);
        SchedulerActivation activation = new SchedulerActivation(
                healthChecker()::verify, loop(new CountDownLatch(1))
        );

        assertThrows(WorkerRuntimeException.class, activation::activate);
        assertFalse(activation.isActive());
        activation.close();
    }

    @Test
    void startsWithoutExternalWorkerCheckForInProcessOnlyRuntime() throws Exception {
        CountDownLatch poll = new CountDownLatch(1);
        SchedulerActivation activation = new SchedulerActivation(() -> { }, loop(poll));

        activation.activate();

        assertTrue(poll.await(1, TimeUnit.SECONDS));
        assertTrue(activation.isActive());
        activation.close();
    }

    private WorkerHealthChecker healthChecker() {
        return new WorkerHealthChecker(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                Duration.ofSeconds(1)
        );
    }

    private CleanSchedulerLoop loop(CountDownLatch poll) {
        TaskExecutionPort tasks = new TaskExecutionPort() {
            @Override
            public TaskExecution claim(String workerId) {
                poll.countDown();
                return null;
            }

            @Override public void recordWorkerEvent(String taskId, WorkerEvent event) { }
            @Override public void succeed(String taskId, String workerId, Map<String, Object> output) { }
            @Override public void fail(String taskId, String workerId, Map<String, Object> error) { }
            @Override public void cancel(String taskId, String workerId, Map<String, Object> detail) { }
        };
        WorkerRuntime worker = new WorkerRuntime() {
            @Override public WorkerJob createJob(String toolId, WorkerJobRequest request) { return null; }
            @Override public WorkerJob getJob(String jobId) { return null; }
            @Override public java.util.List<WorkerEvent> listEvents(String jobId, long afterSequence) { return java.util.List.of(); }
            @Override public void cancelJob(String jobId) { }
        };
        return new CleanSchedulerLoop(
                new CleanScheduler(new TaskDispatcher(tasks, worker)),
                "worker-a", Duration.ofMillis(10), exception -> { }
        );
    }

    private HttpServer start(int status) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/health", exchange -> {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
        });
        server.start();
        return server;
    }
}
