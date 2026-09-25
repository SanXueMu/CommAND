package com.zthcpa.command.runtime.worker;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class HttpWorkerRuntime implements WorkerRuntime {
    private final URI baseUri;
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final Duration timeout;

    public HttpWorkerRuntime(URI baseUri, ObjectMapper mapper, Duration timeout) {
        if (baseUri == null || mapper == null || timeout == null || timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("Worker runtime configuration is invalid");
        }
        this.baseUri = normalize(baseUri);
        this.mapper = mapper;
        this.timeout = timeout;
        this.client = HttpClient.newBuilder().connectTimeout(timeout).build();
    }

    @Override
    public WorkerJob createJob(String toolId, WorkerJobRequest request) {
        require(toolId, "Tool id");
        if (request == null) {
            throw new IllegalArgumentException("Worker request must not be null");
        }
        return readJob(send("POST", path("/v1/tools/" + encode(toolId) + "/jobs"), json(request)));
    }

    @Override
    public WorkerJob getJob(String jobId) {
        require(jobId, "Job id");
        return readJob(send("GET", path("/v1/jobs/" + encode(jobId)), null));
    }

    @Override
    public List<WorkerEvent> listEvents(String jobId, long afterSequence) {
        require(jobId, "Job id");
        if (afterSequence < 0) {
            throw new IllegalArgumentException("After sequence must not be negative");
        }
        JsonNode root = readTree(send("GET", path("/v1/jobs/" + encode(jobId) + "/events?after=" + afterSequence), null));
        JsonNode events = root.isArray() ? root : root.path("events");
        if (!events.isArray()) {
            throw new WorkerRuntimeException("Worker events response must contain an array");
        }
        List<WorkerEvent> result = new ArrayList<>();
        for (JsonNode event : events) {
            result.add(new WorkerEvent(
                    requiredLong(event, "sequence"),
                    requiredText(event, "type"),
                    mapper.convertValue(event.path("data"), Map.class)
            ));
        }
        return List.copyOf(result);
    }

    @Override
    public void cancelJob(String jobId) {
        require(jobId, "Job id");
        send("POST", path("/v1/jobs/" + encode(jobId) + "/cancel"), "{}");
    }

    private WorkerJob readJob(String body) {
        JsonNode root = readTree(body);
        String jobId = requiredText(root, "job_id");
        String status = requiredText(root, "status");
        return new WorkerJob(
                jobId,
                status,
                object(root, "output"),
                object(root, "error")
        );
    }

    private String send(String method, URI uri, String body) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .header("Accept", "application/json");
        if (body == null) {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            builder.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(body));
        }
        try {
            HttpResponse<String> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new WorkerRuntimeException("Worker returned HTTP " + response.statusCode() + ": " + response.body());
            }
            return response.body();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new WorkerRuntimeException("Worker request interrupted", exception);
        } catch (IOException exception) {
            throw new WorkerRuntimeException("Worker request failed: " + uri, exception);
        }
    }

    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new WorkerRuntimeException("Cannot serialize Worker request", exception);
        }
    }

    private JsonNode readTree(String body) {
        try {
            return mapper.readTree(body);
        } catch (JsonProcessingException exception) {
            throw new WorkerRuntimeException("Worker returned invalid JSON", exception);
        }
    }

    private Map<String, Object> object(JsonNode root, String field) {
        JsonNode value = root.get(field);
        return value == null || value.isNull() ? null : mapper.convertValue(value, Map.class);
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            throw new WorkerRuntimeException("Worker response missing " + field);
        }
        return value.asText();
    }

    private static long requiredLong(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.canConvertToLong()) {
            throw new WorkerRuntimeException("Worker event missing " + field);
        }
        return value.asLong();
    }

    private URI path(String path) {
        return baseUri.resolve(path);
    }

    private static URI normalize(URI uri) {
        String value = uri.toString();
        return URI.create(value.endsWith("/") ? value : value + "/");
    }

    private static String encode(String value) {
        return value.replace("%", "%25").replace("/", "%2F").replace(" ", "%20");
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }
}
