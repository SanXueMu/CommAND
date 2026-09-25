package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OpenAiCompatibleLlmClientTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void sendsGenericMessagesAndJsonResponseMode() throws Exception {
        AtomicReference<JsonNode> requestBody = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
            requestBody.set(mapper.readTree(exchange.getRequestBody()));
            byte[] body = mapper.writeValueAsString(Map.of(
                    "model", "provider-model",
                    "choices", List.of(Map.of("message", Map.of("content", "{\"ok\":true}"))),
                    "usage", Map.of("prompt_tokens", 3, "completion_tokens", 2, "total_tokens", 5)
            )).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        var client = client();

        LlmResponse response = client.complete(new LlmRequest(
                "requested-model",
                List.of(new LlmRequest.Message("user", "Classify this")),
                0.1,
                128,
                true
        ));

        assertEquals("{\"ok\":true}", response.content());
        assertEquals("provider-model", response.model());
        assertEquals(5, response.usage().get("total_tokens"));
        assertEquals("json_object", requestBody.get().path("response_format").path("type").asText());
        assertEquals("Classify this", requestBody.get().path("messages").path(0).path("content").asText());
        assertTrue(requestBody.get().has("temperature"));
        assertTrue(requestBody.get().has("max_tokens"));
    }

    private OpenAiCompatibleLlmClient client() throws IOException {
        return new OpenAiCompatibleLlmClient(
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build(),
                mapper,
                URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/v1"),
                "test-key",
                Duration.ofSeconds(1)
        );
    }
}
