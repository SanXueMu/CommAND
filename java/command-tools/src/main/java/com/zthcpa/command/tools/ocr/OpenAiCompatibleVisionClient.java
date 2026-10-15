package com.zthcpa.command.tools.ocr;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.LlmConfigurationPort;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** OpenAI-compatible vision adapter kept separate from the text-only LLM client. */
public final class OpenAiCompatibleVisionClient implements VisionClient {
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final URI endpoint;
    private final String apiKey;
    private final Duration timeout;
    private final LlmConfigurationPort configuration;

    public OpenAiCompatibleVisionClient(HttpClient client, ObjectMapper mapper, URI baseUri, String apiKey, Duration timeout) {
        this.client = client;
        this.mapper = mapper;
        this.endpoint = endpoint(baseUri);
        this.apiKey = required(apiKey, "apiKey");
        this.configuration = null;
        this.timeout = timeout == null ? Duration.ofSeconds(120) : timeout;
    }

    public OpenAiCompatibleVisionClient(HttpClient client, ObjectMapper mapper, LlmConfigurationPort configuration, Duration timeout) {
        this.client = client; this.mapper = mapper; this.configuration = configuration;
        this.endpoint = null; this.apiKey = null; this.timeout = timeout == null ? Duration.ofSeconds(120) : timeout;
    }

    @Override
    public VisionResponse extract(String model, String instruction, String mediaType, String base64Data) {
        try {
            URI requestEndpoint = endpoint;
            String requestApiKey = apiKey;
            if (configuration != null) {
                var settings = configuration.get().orElseThrow(() -> new IllegalStateException("LLM 未配置，请先在系统管理中保存 API Key"));
                requestEndpoint = endpoint(URI.create(settings.baseUrl()));
                requestApiKey = settings.apiKey();
            }
            Map<String, Object> image = Map.of("type", "image_url", "image_url", Map.of("url", "data:" + mediaType + ";base64," + base64Data));
            Map<String, Object> text = Map.of("type", "text", "text", instruction);
            Map<String, Object> message = Map.of("role", "user", "content", List.of(text, image));
            Map<String, Object> body = Map.of("model", required(model, "model"), "messages", List.of(message), "temperature", 0);
            HttpRequest request = HttpRequest.newBuilder(requestEndpoint).timeout(timeout)
                    .header("Authorization", "Bearer " + requestApiKey).header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body))).build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) throw new IllegalStateException("Vision provider returned HTTP " + response.statusCode());
            JsonNode root = mapper.readTree(response.body());
            String content = root.path("choices").path(0).path("message").path("content").asText(null);
            if (content == null) throw new IllegalStateException("Vision response has no message content");
            JsonNode usage = root.path("usage");
            return new VisionResponse(content, root.path("model").asText(model), Map.of(
                    "prompt_tokens", usage.path("prompt_tokens").asInt(0),
                    "completion_tokens", usage.path("completion_tokens").asInt(0),
                    "total_tokens", usage.path("total_tokens").asInt(0)));
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Vision request interrupted", exception);
        } catch (IOException exception) {
            throw new IllegalStateException("Vision request failed", exception);
        }
    }

    private static URI endpoint(URI baseUri) {
        if (baseUri == null) throw new IllegalArgumentException("baseUri must not be null");
        String value = baseUri.toString().replaceAll("/+$", "");
        return URI.create(value.endsWith("/chat/completions") ? value : value + "/chat/completions");
    }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
        return value;
    }
}
