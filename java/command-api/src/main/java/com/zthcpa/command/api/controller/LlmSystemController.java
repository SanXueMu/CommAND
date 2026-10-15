package com.zthcpa.command.api.controller;

import com.zthcpa.command.contract.LlmConfigurationPort;
import com.zthcpa.command.contract.LlmConfigurationPort.LlmApiKey;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/system/llm")
public final class LlmSystemController {
    private final LlmConfigurationPort configuration;

    public LlmSystemController(LlmConfigurationPort configuration) {
        this.configuration = configuration;
    }

    @GetMapping
    public Map<String, Object> status() {
        Map<String, Object> result = new LinkedHashMap<>();
        List<LlmApiKey> keys = configuration.listKeys();
        LlmApiKey defaultKey = keys.stream().filter(LlmApiKey::isDefault).findFirst().orElse(null);
        result.put("enabled", defaultKey != null && defaultKey.enabled());
        result.put("configured", !keys.isEmpty());
        result.put("keyCount", keys.size());
        result.put("defaultKeyId", defaultKey == null ? null : defaultKey.id());
        result.put("baseUrl", defaultKey == null ? "未配置" : maskUrl(defaultKey.baseUrl()));
        result.put("apiKey", defaultKey == null ? "未配置" : "已配置（末四位：" + defaultKey.apiKeySuffix() + "）");
        result.put("model", defaultKey == null ? "未配置" : defaultKey.defaultModel());
        result.put("defaultModel", defaultKey == null ? "未配置" : defaultKey.defaultModel());
        result.put("models", defaultKey == null ? List.of() : defaultKey.models());
        result.put("management", "database");
        result.put("message", "LLM API Key 已加密保存，可管理多个服务密钥和模型列表。");
        return result;
    }

    @GetMapping("/keys")
    public Map<String, Object> keys() {
        return Map.of("items", configuration.listKeys());
    }

    @PostMapping("/keys")
    public ResponseEntity<LlmApiKey> add(@RequestBody KeyRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(configuration.addKey(
                request.remark(), request.providerName(), request.baseUrl(), request.apiKey(),
                request.defaultModel(), request.models(), request.makeDefault()));
    }

    @PutMapping("/keys/{id}")
    public LlmApiKey update(@PathVariable UUID id, @RequestBody KeyRequest request) {
        return configuration.updateKey(id, request.remark(), request.providerName(), request.baseUrl(), request.apiKey(),
                request.defaultModel(), request.models(), request.enabled() == null || request.enabled());
    }

    @PostMapping("/keys/{id}/default")
    public Map<String, Object> setDefault(@PathVariable UUID id) {
        configuration.setDefault(id);
        return status();
    }

    @DeleteMapping("/keys/{id}")
    public ResponseEntity<Void> delete(@PathVariable UUID id) {
        configuration.deleteKey(id);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping
    public ResponseEntity<Void> clear() {
        configuration.clear();
        return ResponseEntity.noContent().build();
    }

    public record KeyRequest(String remark, String providerName, String baseUrl, String apiKey,
                             String defaultModel, List<String> models, Boolean enabled, boolean makeDefault) {}

    private static String maskUrl(String value) {
        try {
            URI uri = URI.create(value);
            return uri.getScheme() + "://" + uri.getHost() + (uri.getPort() > 0 ? ":" + uri.getPort() : "");
        } catch (IllegalArgumentException ignored) {
            return "已配置";
        }
    }
}
