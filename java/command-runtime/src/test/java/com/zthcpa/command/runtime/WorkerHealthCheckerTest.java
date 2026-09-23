package com.zthcpa.command.runtime;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class WorkerHealthCheckerTest {
    private HttpServer runningServer;

    @AfterEach
    void stopServer() {
        if (runningServer != null) {
            runningServer.stop(0);
            runningServer = null;
        }
    }

    @Test
    void acceptsSuccessfulHealthResponse() throws IOException {
        HttpServer server = start(200);
        assertDoesNotThrow(() -> checker(server).verify());
    }

    @Test
    void rejectsNonSuccessfulHealthResponse() throws IOException {
        HttpServer server = start(503);
        assertThrows(WorkerRuntimeException.class, () -> checker(server).verify());
    }

    @Test
    void reportsConnectionFailure() {
        WorkerHealthChecker checker = new WorkerHealthChecker(
                URI.create("http://127.0.0.1:1"), Duration.ofMillis(100)
        );

        assertThrows(WorkerRuntimeException.class, checker::verify);
    }

    private static WorkerHealthChecker checker(HttpServer server) {
        return new WorkerHealthChecker(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                Duration.ofSeconds(1)
        );
    }

    private static HttpServer server(int status) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/health", exchange -> {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
        });
        return server;
    }

    private HttpServer start(int status) throws IOException {
        runningServer = server(status);
        runningServer.start();
        return runningServer;
    }
}
