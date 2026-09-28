package com.zthcpa.command.api.controller;

import com.zthcpa.command.persistence.ocr.OcrPersistenceService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/ocr")
public final class OcrController {
    private final OcrPersistenceService persistence;

    public OcrController(OcrPersistenceService persistence) { this.persistence = persistence; }

    @GetMapping("/templates")
    public Map<String, Object> templates() {
        List<Map<String, Object>> templates = persistence.templates();
        return Map.of("templates", templates, "total", templates.size());
    }

    @PostMapping("/templates")
    public ResponseEntity<Map<String, Object>> saveTemplate(@RequestBody Map<String, Object> body) { return ResponseEntity.ok(persistence.saveTemplate(body)); }

    @DeleteMapping("/templates/{id}/{version}")
    public ResponseEntity<Void> deleteTemplate(@PathVariable String id, @PathVariable int version) { persistence.deleteTemplate(id, version); return ResponseEntity.noContent().build(); }

    @GetMapping("/results")
    public Map<String, Object> results() { List<Map<String, Object>> results = persistence.resultSets(); return Map.of("dbs", results, "total", results.size()); }

    @GetMapping("/records")
    public Map<String, Object> records(@RequestParam(required = false) String resultSetId) { List<Map<String, Object>> records = persistence.records(resultSetId); return Map.of("rows", records, "total", records.size()); }

    @GetMapping("/views")
    public Map<String, Object> views() { List<Map<String, Object>> views = persistence.views(); return Map.of("views", views, "total", views.size()); }

    @PostMapping("/views")
    public ResponseEntity<Map<String, Object>> saveView(@RequestBody Map<String, Object> body) { return ResponseEntity.ok(persistence.saveView(body)); }

    @DeleteMapping("/views/{id}")
    public ResponseEntity<Void> deleteView(@PathVariable String id) { persistence.deleteView(id); return ResponseEntity.noContent().build(); }
}
