package com.zthcpa.command.tools;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * OpenAI-compatible chat adapter. Credentials stay outside the tool and are
 * supplied by application configuration.
 */
public final class OpenAiCompatibleTranslationModel implements TranslationModel {
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final URI endpoint;
    private final String apiKey;
    private final Duration timeout;

    public OpenAiCompatibleTranslationModel(
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
        this.timeout = timeout == null ? Duration.ofSeconds(120) : timeout;
    }

    @Override
    public TranslationBatch translate(
            List<String> segments,
            TranslationOptions options,
            ProgressSink progress
    ) {
        if (segments.isEmpty()) {
            return new TranslationBatch(List.of(), new TranslationBatch.Usage(0, 0));
        }
        try {
            ChatResponse response = request(separatorPayload(segments, options), options.model(), false);
            List<String> translated = parseSeparator(response.content(), segments.size());
            if (translated != null) {
                progress.emit(Map.of("phase", "model", "route", "separator", "count", segments.size()));
                return items(segments, translated, options.model(), response.usage());
            }

            ChatResponse fallback = request(jsonPayload(segments, options), options.fallbackModel(), true);
            List<String> jsonTranslated = parseJson(fallback.content(), segments.size());
            if (jsonTranslated == null) {
                throw new TextLlmTranslateTool.TranslationToolException(
                        "Model response could not be aligned with input segments"
                );
            }
            progress.emit(Map.of("phase", "model", "route", "json", "count", segments.size()));
            return items(segments, jsonTranslated, options.fallbackModel(), fallback.usage());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new TextLlmTranslateTool.TranslationToolException("Translation model request interrupted");
        } catch (IOException exception) {
            throw new TextLlmTranslateTool.TranslationToolException(
                    "Translation model request failed: " + exception.getMessage()
            );
        }
    }

    private ChatResponse request(Map<String, Object> payload, String model, boolean jsonMode)
            throws IOException, InterruptedException {
        Map<String, Object> body = new HashMap<>();
        body.put("model", model);
        body.put("messages", List.of(Map.of("role", "user", "content", payload.get("prompt"))));
        if (jsonMode) {
            body.put("response_format", Map.of("type", "json_object"));
        }
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(timeout)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)))
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new TextLlmTranslateTool.TranslationToolException(
                    "Translation model returned HTTP " + response.statusCode()
            );
        }
        JsonNode root = mapper.readTree(response.body());
        String content = root.path("choices").path(0).path("message").path("content").asText(null);
        if (content == null) {
            throw new TextLlmTranslateTool.TranslationToolException(
                    "Translation model response has no message content"
            );
        }
        JsonNode usage = root.path("usage");
        return new ChatResponse(content, new TranslationBatch.Usage(
                usage.path("prompt_tokens").asInt(0), usage.path("completion_tokens").asInt(0)
        ));
    }

    private Map<String, Object> separatorPayload(List<String> segments, TranslationOptions options) {
        StringBuilder prompt = new StringBuilder(systemPrompt(options));
        for (int i = 0; i < segments.size(); i++) {
            prompt.append("\n###").append(i + 1).append("###\n").append(segments.get(i));
        }
        return Map.of("prompt", prompt.toString());
    }

    private Map<String, Object> jsonPayload(List<String> segments, TranslationOptions options) throws IOException {
        List<Map<String, Object>> items = new ArrayList<>();
        for (int i = 0; i < segments.size(); i++) {
            items.add(Map.of("id", i + 1, "text", segments.get(i)));
        }
        return Map.of("prompt", systemPrompt(options) +
                " Return JSON only as {\"translations\":[{\"id\":1,\"text\":\"...\"}]} for this input: " +
                mapper.writeValueAsString(items));
    }

    private String systemPrompt(TranslationOptions options) {
        String glossary = options.terms().isEmpty() ? "" : " Glossary: " + options.terms().stream()
                .map(term -> term.source() + " -> " + term.target())
                .reduce((left, right) -> left + "; " + right)
                .orElse("") + ".";
        return "Translate into " + options.targetLanguage() + ". Preserve numbers, codes, names, and placeholders." + glossary;
    }

    private List<String> parseSeparator(String content, int count) {
        List<String> result = new ArrayList<>();
        for (int i = 1; i <= count; i++) {
            String marker = "###" + i + "###";
            int start = content.indexOf(marker);
            if (start < 0) return null;
            start += marker.length();
            int end = i == count ? content.length() : content.indexOf("###" + (i + 1) + "###", start);
            if (end < 0) return null;
            result.add(content.substring(start, end).trim());
        }
        return result;
    }

    private List<String> parseJson(String content, int count) throws IOException {
        JsonNode root = mapper.readTree(content);
        JsonNode values = root.isArray() ? root : root.path("translations");
        if (!values.isArray() || values.size() != count) return null;
        List<String> result = new ArrayList<>();
        for (JsonNode value : values) {
            JsonNode text = value.has("text")
                    ? value.get("text")
                    : value.has("translation") ? value.get("translation") : value.get("zh");
            if (text == null || !text.isTextual()) return null;
            result.add(text.textValue());
        }
        return result;
    }

    private TranslationBatch items(
            List<String> sources,
            List<String> translated,
            String model,
            TranslationBatch.Usage usage
    ) {
        List<TranslationBatch.TranslationItem> items = new ArrayList<>();
        for (int i = 0; i < sources.size(); i++) {
            items.add(new TranslationBatch.TranslationItem(sources.get(i), translated.get(i), "ok", model));
        }
        return new TranslationBatch(items, usage);
    }

    private URI endpoint(URI baseUri) {
        if (baseUri == null) throw new IllegalArgumentException("baseUri must not be null");
        String value = baseUri.toString().replaceAll("/+$", "");
        return URI.create(value.endsWith("/chat/completions") ? value : value + "/chat/completions");
    }

    private String require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
        return value;
    }

    private record ChatResponse(String content, TranslationBatch.Usage usage) { }
}
