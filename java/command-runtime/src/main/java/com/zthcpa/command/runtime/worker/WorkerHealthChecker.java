package com.zthcpa.command.runtime.worker;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class WorkerHealthChecker {
    private final URI healthUri;
    private final HttpClient client;
    private final Duration timeout;

    public WorkerHealthChecker(URI workerBaseUri, Duration timeout) {
        if (workerBaseUri == null || timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("Worker health configuration is invalid");
        }
        this.healthUri = normalize(workerBaseUri).resolve("health");
        this.timeout = timeout;
        this.client = HttpClient.newBuilder().connectTimeout(timeout).build();
    }

    public void verify() {
        HttpRequest request = HttpRequest.newBuilder(healthUri)
                .timeout(timeout)
                .header("Accept", "application/json")
                .GET()
                .build();
        try {
            HttpResponse<Void> response = client.send(request, HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new WorkerRuntimeException("Worker health check returned HTTP " + response.statusCode());
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new WorkerRuntimeException("Worker health check interrupted", exception);
        } catch (IOException exception) {
            throw new WorkerRuntimeException("Worker health check failed: " + healthUri, exception);
        }
    }

    private static URI normalize(URI uri) {
        String value = uri.toString();
        return URI.create(value.endsWith("/") ? value : value + "/");
    }
}
