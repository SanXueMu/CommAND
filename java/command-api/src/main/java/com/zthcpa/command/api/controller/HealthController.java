package com.zthcpa.command.api.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public final class HealthController {
    @GetMapping({"/health", "/api/health"})
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
