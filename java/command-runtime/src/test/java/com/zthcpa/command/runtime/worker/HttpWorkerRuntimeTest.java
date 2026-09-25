package com.zthcpa.command.runtime.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HttpWorkerRuntimeTest {
    private HttpServer server;
    private AtomicReference<String> lastRequest;
    private HttpWorkerRuntime runtime;

    @BeforeEach
    void setUp() throws IOException {
        lastRequest = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/", this::handle);
        server.start();
        runtime = new HttpWorkerRuntime(
                URI.create("http://localhost:" + server.getAddress().getPort()),
                new ObjectMapper(), Duration.ofSeconds(2)
        );
    }

    @AfterEach
    void tearDown() {
        server.stop(0);
    }

    @Test
    void createsReadsEventsAndCancelsWorkerJob() {
        WorkerJob created = runtime.createJob("llm.chat.complete", new WorkerJobRequest(
                "llm.chat.complete", "task-1", 1, Map.of("text", "hello")
        ));
        assertEquals("job-1", created.jobId());
        assertEquals("queued", created.status());

        assertEquals("succeeded", runtime.getJob("job-1").status());
        List<WorkerEvent> events = runtime.listEvents("job-1", 3);
        assertEquals(1, events.size());
        assertEquals(4, events.get(0).sequence());
        runtime.cancelJob("job-1");
        assertEquals("POST /v1/jobs/job-1/cancel", lastRequest.get());
    }

    @Test
    void rejectsWorkerHttpErrors() {
        server.createContext("/v1/jobs/error", exchange -> respond(exchange, 503, "busy"));
        assertThrows(WorkerRuntimeException.class, () -> runtime.getJob("error"));
    }

    private void handle(HttpExchange exchange) throws IOException {
        String request = exchange.getRequestMethod() + " " + exchange.getRequestURI();
        lastRequest.set(request);
        String path = exchange.getRequestURI().getPath();
        if (path.equals("/v1/tools/llm.chat.complete/jobs")) {
            respond(exchange, 202, "{\"job_id\":\"job-1\",\"status\":\"queued\"}");
        } else if (path.equals("/v1/jobs/job-1")) {
            respond(exchange, 200, "{\"job_id\":\"job-1\",\"status\":\"succeeded\",\"output\":{\"text\":\"你好\"}}");
        } else if (path.equals("/v1/jobs/job-1/events")) {
            respond(exchange, 200, "{\"events\":[{\"sequence\":4,\"type\":\"completed\",\"data\":{\"percent\":100}}]}");
        } else if (path.equals("/v1/jobs/job-1/cancel")) {
            respond(exchange, 202, "{}");
        } else {
            respond(exchange, 404, "missing");
        }
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
