package com.zthcpa.command.api.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Root-level CommWEB handshake endpoints. Business APIs remain under /api. */
@RestController
public final class CommWebProtocolController {
    private final CatalogController catalog;

    public CommWebProtocolController(CatalogController catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/meta/protocol")
    public Map<String, Object> protocol() {
        return Map.of(
                "core", 1,
                "extensions", Map.of("registry", 1, "form.fields", 1)
        );
    }

    @GetMapping("/meta/site")
    public Map<String, Object> site() {
        return catalog.site();
    }

    @GetMapping("/meta/registry")
    public Map<String, Object> registry() {
        return catalog.registry();
    }
}
