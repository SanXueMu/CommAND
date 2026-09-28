package com.zthcpa.command.api.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.contract.ToolDescriptor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.io.IOException;
import java.io.InputStream;

@RestController
@RequestMapping("/api")
public final class CatalogController {
    private final ToolCatalog catalog;
    private final ObjectMapper objectMapper;

    public CatalogController(ToolCatalog catalog, ObjectMapper objectMapper) {
        this.catalog = catalog;
        this.objectMapper = objectMapper;
    }

    @GetMapping("/meta/site")
    public Map<String, Object> site() {
        Map<String, Object> manifest = Map.of(
                "member", "command",
                "name", "CommAND Java Platform",
                "version", "1",
                "views", List.of(
                        view("tools", "工具目录", "tools.grid", "appstore-outlined"),
                        view("tasks", "运行任务", "tasks.table", "unordered-list-outlined"),
                        view("workspace", "工作台", "workspace.tabs", "desktop-outlined"),
                        Map.of("id", "translate", "title", "翻译工作台", "type", "translate.studio",
                                "icon", "translation-outlined", "default", true,
                                "props", Map.of(
                                        "description", "文本翻译、术语和翻译任务管理",
                                        "flow_prefix", "translate.",
                                        "routes", List.of(Map.of("ext", List.of(".txt", ".md"), "flow", "translate.text", "label", "文本翻译")),
                                        "languages", List.of(
                                                Map.of("value", "Chinese", "label", "中文"),
                                                Map.of("value", "English", "label", "English"),
                                                Map.of("value", "Japanese", "label", "日本語"),
                                                Map.of("value", "Korean", "label", "한국어")
                                        ),
                                        "params", List.of(Map.of("name", "model", "label", "模型", "type", "text", "default", "deepseek-v3.2")),
                                         "unsupported", List.of(Map.of("ext", List.of(".doc", ".pdf", ".xlsx", ".docx"), "message", "该文件类型正在接入文件适配器"))
                                )),
                        Map.of("id", "ocr", "title", "OCR 工作台", "type", "ocr.studio",
                                "icon", "scan-outlined", "sort", 50,
                                "props", Map.of(
                                        "nav", Map.of("kind", "child", "group", "work", "label", "OCR 工作台"),
                                        "description", "模板驱动识别、结果预览和批量任务",
                                        "recognizeFlow", "ocr.extract-document",
                                        "flows", List.of("ocr.extract-document", "ocr.extract-by-template"),
                                        "viewTool", "records.view.query",
                                        "templatesPath", "/ocr/templates",
                                        "recordsPath", "/ocr/records",
                                        "dbsPath", "/ocr/results",
                                        "batch", Map.of("extensions", List.of(".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"), "maxFiles", 200, "maxTotalMB", 500),
                                         "records", Map.of("export", true, "exportFlow", "records.export.xlsx")
                                ))
                )
        );
        return Map.of("site", manifest);
    }

    @GetMapping("/tools")
    public Map<String, Object> tools() {
        List<Map<String, Object>> items = catalog.list().stream()
                .filter(tool -> "active".equalsIgnoreCase(tool.status()))
                .map(this::toolSummary)
                .toList();
        return Map.of("tools", items);
    }

    /** Read-only compatibility projection consumed by the current CommWEB translation view. */
    @GetMapping("/pipelines")
    public Map<String, Object> pipelines() {
        return Map.of("pipelines", List.of(Map.of(
                "id", "translate.text",
                "name", "文本翻译",
                "type", "workflow",
                "steps", List.of(Map.of("tool", "text.translate", "input", Map.of())),
                "input_schema", Map.of("type", "object", "required", List.of("text", "target_lang", "model")),
                "doc_md", "将输入文本翻译为指定目标语言，保留占位符、数字和段落结构。"
        ), Map.of(
                "id", "ocr.extract-document",
                "name", "OCR 文档识别",
                "type", "workflow",
                "steps", List.of(Map.of("tool", "ocr.extract-by-template", "input", Map.of())),
                "input_schema", Map.of("type", "object", "required", List.of("file", "template_id")),
                "doc_md", "按模板识别文档并保留结构化结果。"
        )));
    }

    @GetMapping("/translate/templates")
    public Map<String, Object> translateTemplates() {
        return Map.of("templates", List.of(Map.of(
                "id", "builtin.translate.general",
                "name", "通用文本翻译",
                "desc", "保留数字、占位符和段落结构",
                "source_lang", "",
                "target_lang", "Chinese",
                "model", "deepseek-v3.2",
                "builtin", true,
                "terms", List.of()
        )));
    }

    @GetMapping("/translate/dict")
    public Map<String, Object> translateDictionary() {
        return Map.of("rows", List.of(), "total", 0,
                "stats", Map.of("ok", 0, "review", 0));
    }

    @GetMapping("/tools/{toolId}")
    public Map<String, Object> tool(@PathVariable String toolId) {
        Map<String, Object> item = catalog.list().stream()
                .filter(tool -> tool.key().id().equals(toolId))
                .findFirst()
                .map(this::toolSummary)
                .orElseThrow(() -> new IllegalArgumentException("Tool not found: " + toolId));
        return item;
    }

    @GetMapping("/meta/tool-categories")
    public Map<String, Object> categories() {
        Map<String, List<String>> grouped = new LinkedHashMap<>();
        catalog.list().stream()
                .filter(tool -> "active".equalsIgnoreCase(tool.status()))
                .map(this::toolSummary)
                .forEach(tool -> {
                    String category = String.valueOf(tool.get("category"));
                    String subcategory = String.valueOf(tool.get("subcategory"));
                    grouped.computeIfAbsent(category, ignored -> new java.util.ArrayList<>());
                    if (!"null".equals(subcategory)) {
                        grouped.get(category).add(subcategory);
                    }
                });
        return Map.of("categories", grouped.entrySet().stream()
                .map(entry -> Map.of("name", entry.getKey(), "subs", entry.getValue().stream().distinct().toList()))
                .toList());
    }

    private Map<String, Object> toolSummary(ToolDescriptor descriptor) {
        Map<String, Object> manifest = descriptor.manifest();
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", descriptor.key().id());
        item.put("name", firstText(manifest, "title", descriptor.key().id()));
        item.put("version", String.valueOf(descriptor.key().version()));
        item.put("description", firstText(manifest, "description", "Java Tool"));
        item.put("input_types", List.of("json"));
        item.put("output_types", List.of("json"));
        item.put("runtime_kind", descriptor.runtimeKind().value());
        item.put("migration_status", descriptor.runtimeKind().value().equals("inproc")
                ? "java_migrated" : "http_adapter_pending");
        item.put("enabled", "active".equalsIgnoreCase(descriptor.status()));
        item.put("hidden", false);
        item.put("category", category(descriptor.key().id()));
        item.put("subcategory", descriptor.key().id().split("\\.")[0]);
        item.put("manifest", frontendManifest(manifest));
        return item;
    }

    private Map<String, Object> frontendManifest(Map<String, Object> source) {
        Map<String, Object> manifest = new LinkedHashMap<>(source);
        Map<String, Object> io = new LinkedHashMap<>();
        io.put("input_schema", readSchema(source.get("input_schema")));
        io.put("output_schema", readSchema(source.get("output_schema")));
        io.put("input_types", List.of("json"));
        io.put("output_types", List.of("json"));
        manifest.put("io", io);
        manifest.put("runtime", Map.of("kind", source.getOrDefault("runtime", "http")));
        manifest.put("ui", Map.of());
        return manifest;
    }

    private Object readSchema(Object resource) {
        if (!(resource instanceof String path) || path.isBlank()) {
            return Map.of("type", "object");
        }
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(path)) {
            if (input == null) {
                return Map.of("type", "object");
            }
            return objectMapper.readValue(input, Object.class);
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to load tool schema: " + path, exception);
        }
    }

    private static Map<String, Object> view(String id, String title, String type, String icon) {
        return Map.of("id", id, "title", title, "type", type, "icon", icon);
    }

    private static String firstText(Map<String, Object> manifest, String key, String fallback) {
        Object value = manifest.get(key);
        return value instanceof String text && !text.isBlank() ? text : fallback;
    }

    private static String category(String toolId) {
        if (toolId.startsWith("llm.")) return "大模型";
        if (toolId.startsWith("ocr.")) return "文档识别";
        if (toolId.startsWith("records.")) return "记录处理";
        if (toolId.startsWith("table.")) return "表格处理";
        if (toolId.startsWith("txt.") || toolId.startsWith("text.")) return "文本处理";
        return "其他工具";
    }
}
