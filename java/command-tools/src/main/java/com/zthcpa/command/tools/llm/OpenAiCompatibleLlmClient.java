package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.LlmConfigurationPort;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OpenAiCompatibleLlmClient implements LlmClient {
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final URI endpoint;
    private final String apiKey;
    private final LlmConfigurationPort configuration;
    private final Duration timeout;

    public OpenAiCompatibleLlmClient(
            HttpClient client,
            ObjectMapper mapper,
            URI baseUri,
            String apiKey,
            Duration timeout
    ) {
        this.client = client;
        this.mapper = mapper;
        this.endpoint = endpoint(baseUri);
        this.apiKey = require(apiKey, "apiKey");
        this.configuration = null;
        this.timeout = timeout == null ? Duration.ofSeconds(120) : timeout;
    }

    public OpenAiCompatibleLlmClient(HttpClient client, ObjectMapper mapper, LlmConfigurationPort configuration, Duration timeout) {
        this.client = client; this.mapper = mapper; this.configuration = configuration;
        this.endpoint = null; this.apiKey = null; this.timeout = timeout == null ? Duration.ofSeconds(120) : timeout;
    }

    @Override
    public LlmResponse complete(LlmRequest request) {
        try {
            URI requestEndpoint = endpoint;
            String requestApiKey = apiKey;
            if (configuration != null) {
                var settings = configuration.get().orElseThrow(() -> new LlmToolException("LLM 未配置，请先在系统管理中保存 API Key"));
                requestEndpoint = endpoint(URI.create(settings.baseUrl()));
                requestApiKey = settings.apiKey();
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("model", request.model());
            body.put("messages", request.messages().stream()
                    .map(message -> Map.of("role", message.role(), "content", message.content()))
                    .toList());
            if (request.temperature() != null) {
                body.put("temperature", request.temperature());
            }
            if (request.maxTokens() != null) {
                body.put("max_tokens", request.maxTokens());
            }
            if (request.jsonObject()) {
                body.put("response_format", Map.of("type", "json_object"));
            }

            HttpRequest httpRequest = HttpRequest.newBuilder(requestEndpoint)
                    .timeout(timeout)
                    .header("Authorization", "Bearer " + requestApiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)))
                    .build();
            HttpResponse<String> response = client.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new LlmToolException("LLM provider returned HTTP " + response.statusCode());
            }
            JsonNode root = mapper.readTree(response.body());
            String content = root.path("choices").path(0).path("message").path("content").asText(null);
            if (content == null) {
                throw new LlmToolException("LLM provider response has no message content");
            }
            JsonNode usage = root.path("usage");
            Map<String, Object> usageValues = Map.of(
                    "prompt_tokens", usage.path("prompt_tokens").asInt(0),
                    "completion_tokens", usage.path("completion_tokens").asInt(0),
                    "total_tokens", usage.path("total_tokens").asInt(0)
            );
            return new LlmResponse(content, root.path("model").asText(request.model()), usageValues);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new LlmToolException("LLM request interrupted", exception);
        } catch (IOException exception) {
            throw new LlmToolException("LLM request failed: " + exception.getMessage(), exception);
        }
    }

    private static URI endpoint(URI baseUri) {
        if (baseUri == null) {
            throw new IllegalArgumentException("baseUri must not be null");
        }
        String value = baseUri.toString().replaceAll("/+$", "");
        return URI.create(value.endsWith("/chat/completions") ? value : value + "/chat/completions");
    }

    private static String require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }
}
