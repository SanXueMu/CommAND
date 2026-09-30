package com.zthcpa.command.api.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.api.model.RunApiModels;
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
    private final DefinitionRegistry definitions;

    public CatalogController(ToolCatalog catalog, ObjectMapper objectMapper, DefinitionRegistry definitions) {
        this.catalog = catalog;
        this.objectMapper = objectMapper;
        this.definitions = definitions;
    }

    @GetMapping("/meta/site")
    public Map<String, Object> site() {
        Map<String, Object> manifest = Map.of(
                "member", "command",
                "name", "CommAND Java Platform",
                "version", "1",
                "views", List.of(
                        view("capabilities", "工具与工作流", "resource", "appstore-outlined"),
                        view("tasks", "任务中心", "console", "unordered-list-outlined"),
                        view("workbenches", "工作台", "workbench", "desktop-outlined"),
                         studioView("translate", "翻译工作台", "translate.studio", "translation-outlined", true,
                                 new LinkedHashMap<>(Map.of(
                                        "description", "文本翻译、术语和翻译任务管理",
                                        "flow_prefix", "translate.",
                                         "routes", List.of(
                                                 Map.of("ext", List.of(".txt", ".md"), "flow", "translate.text", "label", "文本翻译", "state", "available"),
                                                 Map.of("ext", List.of(".pdf", ".docx", ".xlsx"), "flow", "translate.document", "label", "文档翻译", "state", "adapter_pending")
                                         ),
                                        "languages", List.of(
                                                Map.of("value", "Chinese", "label", "中文"),
                                                Map.of("value", "English", "label", "English"),
                                                Map.of("value", "Japanese", "label", "日本語"),
                                                Map.of("value", "Korean", "label", "한국어")
                                        ),
                                         "params", List.of(
                                                 Map.of("name", "model", "label", "模型", "type", "text", "default", "deepseek-v3.2"),
                                                 Map.of("name", "domain_hint", "label", "业务领域", "type", "text", "default", ""),
                                                 Map.of("name", "terms", "label", "术语表", "type", "table", "default", List.of())
                                         ),
                                         "batch", Map.of("maxFiles", 200, "maxTotalMB", 500, "state", "text_available_document_adapter_pending"),
                                         "templatesPath", "/api/translate/templates",
                                         "dictionaryPath", "/api/translate/dict",
                                         "unsupported", List.of(Map.of("ext", List.of(".doc", ".pdf", ".xlsx", ".docx"), "message", "该文件类型正在接入文件适配器"))
                                 ))),
                         studioView("ocr", "OCR 工作台", "ocr.studio", "scan-outlined", false,
                                  new LinkedHashMap<>(Map.ofEntries(
                                         Map.entry("nav", Map.of("kind", "child", "group", "work", "label", "OCR 工作台")),
                                         Map.entry("description", "模板驱动识别、结果预览和批量任务"),
                                         Map.entry("recognizeFlow", "ocr.extract-document"),
                                         Map.entry("flows", List.of("ocr.extract-document", "ocr.extract-by-template")),
                                         Map.entry("viewTool", "records.view.query"),
                                         Map.entry("templatesPath", "/ocr/templates"),
                                         Map.entry("recordsPath", "/ocr/records"),
                                         Map.entry("dbsPath", "/ocr/results"),
                                         Map.entry("batch", Map.of("extensions", List.of(".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"), "maxFiles", 200, "maxTotalMB", 500)),
                                         Map.entry("records", Map.of("export", true, "exportFlow", "records.export.xlsx", "formats", List.of("xlsx", "csv"))),
                                         Map.entry("views", Map.of("listPath", "/api/ocr/views", "queryFlow", "records.view.query")),
                                         Map.entry("preview", Map.of("page", true, "records", true, "state", "available"))
                                  )))
                )
        );
        return Map.of("site", manifest);
    }

    @GetMapping("/meta/registry")
    public Map<String, Object> registry() {
        return Map.of(
                "registry", Map.of("version", "2", "protocolVersion", "component-framework-page-2"),
                "pages", List.of(
                        page("capabilities", "工具与工作流", "resource", "appstore-outlined", true,
                                List.of(
                                        component("capabilities-header", "page-header", "header", Map.of("title", "工具与工作流", "description", "统一查看可执行工具和工作流")),
                                         component("capabilities-toolbar", "toolbar", "toolbar", Map.of(
                                                 "title", "能力类型",
                                                 "filters", List.of(Map.of("key", "kind", "label", "工具"), Map.of("key", "kind", "label", "工作流")),
                                                 "searchResource", "capabilities",
                                                 "searchPlaceholder", "搜索工具名称、工作流名称或用途"
                                         )),
                                         component("capabilities-table", "data-table", "main", Map.of(
                                                 "title", "能力目录",
                                                 "searchable", true,
                                                 "columns", List.of(
                                                         Map.of("key", "name", "label", "名称"),
                                                         Map.of("key", "kindLabel", "label", "类型"),
                                                         Map.of("key", "description", "label", "用途"),
                                                         Map.of("key", "runtimeLabel", "label", "运行方式"),
                                                         Map.of("key", "statusLabel", "label", "状态"),
                                                         Map.of("key", "stepsLabel", "label", "步骤")
                                                 )
                                         ), "capabilities"),
                                         component("capabilities-detail", "detail-panel", "detail", Map.of("title", "能力详情", "drawer", true), "capability-detail")
                                )),
                         page("tasks", "任务中心", "console", "unordered-list-outlined", false,
                                 List.of(
                                         component("tasks-sidebar", "sidebar", "sidebar", Map.of(
                                                 "title", "任务筛选",
                                                 "items", List.of(
                                                         Map.of("key", "all", "label", "全部运行"),
                                                         Map.of("key", "running", "label", "运行中"),
                                                          Map.of("key", "queued", "label", "排队中"),
                                                          Map.of("key", "succeeded", "label", "已完成"),
                                                          Map.of("key", "failed", "label", "失败"),
                                                          Map.of("key", "cancelled", "label", "已取消"),
                                                          Map.of("key", "interrupted", "label", "已中断")
                                                 )
                                         )),
                                          component("tasks-header", "page-header", "header", Map.of("title", "任务中心", "description", "查看运行、步骤、事件和产物")),
                                          component("tasks-toolbar", "toolbar", "header", Map.of("title", "运行筛选", "searchPlaceholder", "搜索运行编号或工作流", "searchResource", "runs")),
                                          component("tasks-table", "data-table", "main", Map.of("title", "运行记录", "columns", List.of(
                                                 Map.of("key", "displayId", "label", "运行记录"),
                                                  Map.of("key", "workflowName", "label", "工作流"),
                                                  Map.of("key", "statusLabel", "label", "状态"),
                                                  Map.of("key", "progressPercent", "label", "进度"),
                                                  Map.of("key", "currentStep", "label", "当前步骤"),
                                                  Map.of("key", "createdAt", "label", "创建时间")
                                         ), "searchable", true), "runs"),
                                         component("task-detail-summary", "detail-panel", "detail", Map.of("title", "运行摘要", "drawer", true), "active-run"),
                                         component("task-detail-progress", "progress-panel", "detail", Map.of("title", "步骤进度"), "active-run"),
                                         component("task-detail-result", "result-preview", "detail", Map.of("title", "节点结果"), "active-run"),
                                         component("task-detail-timeline", "timeline", "detail", Map.of("title", "事件时间线"), "run-events")
                                )),
                        page("workbenches", "工作台", "workbench", "desktop-outlined", false,
                                List.of(
                                        component("workbench-header", "page-header", "header", Map.of("title", "工作台", "description", "选择工作台并提交正式工作流运行")),
                                         component("workbench-form", "form", "input", Map.of("title", "工作台输入", "description", "选择工作流、上传文件或输入文本，然后提交任务", "fields", List.of("workflowId", "input"), "workbenches", List.of(
                                                  Map.of("id", "ocr.extract-document", "title", "OCR 文档提取", "description", "上传 PDF 或图片，查看页面、识别字段和结果表格", "inputMode", "file", "accept", ".pdf,.png,.jpg,.jpeg"),
                                                  Map.of("id", "translate.text", "title", "文本翻译", "description", "输入文本，设置语言和术语，查看最终译文", "inputMode", "text"),
                                                  Map.of("id", "image.transform", "title", "图片翻转", "description", "上传图片并查看翻转后的真实结果", "inputMode", "image", "accept", ".png,.jpg,.jpeg", "operations", List.of("flip_horizontal", "flip_vertical"))
                                          ))),
                                         component("workbench-progress", "progress-panel", "status", Map.of("title", "运行进度"), "active-run"),
                                         component("workbench-result", "result-preview", "result", Map.of("title", "节点结果"), "active-run"),
                                          component("workbench-resources", "tabs", "result", Map.of("title", "资料与结果", "items", List.of(
                                                 Map.of("id", "ocr-templates", "label", "OCR 模板", "resource", "ocr-templates"),
                                                 Map.of("id", "ocr-results", "label", "OCR 结果库", "resource", "ocr-results"),
                                                 Map.of("id", "translate-templates", "label", "翻译模板", "resource", "translate-templates"),
                                                 Map.of("id", "translate-dictionary", "label", "翻译字典", "resource", "translate-dictionary")
                                         )))
                                ))
                ),
                "resources", Map.of("version", "1", "resources", List.of(
                        resource("capabilities", "工具与工作流", "/api/capabilities"),
                        resource("runs", "运行记录", "/api/runs"),
                        resource("run-events", "运行事件", "/api/runs/{runId}/events"),
                        resource("active-run", "运行详情", "/api/runs/{runId}"),
                         resource("capability-detail", "能力详情", "/api/capabilities/{capabilityId}"),
                         resource("ocr-templates", "OCR 模板", "/api/ocr/templates"),
                         resource("ocr-results", "OCR 结果库", "/api/ocr/results"),
                         resource("ocr-records", "OCR 记录", "/api/ocr/records"),
                         resource("ocr-views", "OCR 视图", "/api/ocr/views"),
                         resource("translate-templates", "翻译模板", "/api/translate/templates"),
                         resource("translate-dictionary", "翻译字典", "/api/translate/dict")
                 )),
                 "actions", Map.of("version", "1", "actions", List.of(
                          action("submit-run", "提交运行", "POST", "/api/runs"),
                          action("upload-file", "上传文件", "POST", "/api/files/upload"),
                          action("cancel-run", "取消运行", "POST", "/api/runs/{runId}/cancel"),
                                         action("recover-run", "恢复运行", "POST", "/api/runs/{runId}/recover")
                ))
        );
    }

    @GetMapping("/tools")
    public Map<String, Object> tools() {
        List<Map<String, Object>> items = catalog.list().stream()
                .filter(tool -> "active".equalsIgnoreCase(tool.status()))
                .map(this::toolSummary)
                .toList();
        return Map.of("tools", items);
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities() {
        List<Map<String, Object>> items = new java.util.ArrayList<>();
        catalog.list().stream().filter(tool -> "active".equalsIgnoreCase(tool.status()))
                .map(tool -> {
                    Map<String, Object> item = new LinkedHashMap<>(toolSummary(tool));
                    item.put("kind", "tool");
                    item.put("runnable", "inproc".equals(item.get("runtime_kind")));
                    item.put("steps", 1);
                    return item;
                }).forEach(items::add);
        definitions.list(DefinitionKind.WORKFLOW).stream().filter(d -> d.status().value().equals("active"))
                .map(this::workflowSummary).forEach(items::add);
        return Map.of("capabilities", items);
    }

    @GetMapping("/capabilities/{capabilityId}")
    public Map<String, Object> capability(@PathVariable String capabilityId) {
        Map<String, Object> capability = capabilities().get("capabilities") instanceof List<?> list
                ? list.stream().filter(Map.class::isInstance).map(value -> (Map<?, ?>) value)
                .filter(item -> capabilityId.equals(String.valueOf(item.get("id")))).findFirst()
                .map(item -> new LinkedHashMap<String, Object>() {{
                    item.forEach((key, value) -> put(String.valueOf(key), value));
                }}).orElse(null) : null;
        if (capability == null) throw new IllegalArgumentException("Capability not found: " + capabilityId);
        return capability;
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
         item.put("name", displayName(descriptor.key().id(), firstText(manifest, "title", descriptor.key().id())));
        item.put("version", String.valueOf(descriptor.key().version()));
         item.put("description", firstText(manifest, "description", "Java Tool"));
          item.put("purpose", purpose(descriptor.key().id(), firstText(manifest, "description", "提供可复用的原子处理能力。")));
         item.put("principle", "由 CommAND Runtime 按 Tool Catalog 声明调度，并以结构化输入输出完成一次原子处理。");
        item.put("input_types", List.of("json"));
        item.put("output_types", List.of("json"));
         item.put("runtime_kind", descriptor.runtimeKind().value());
         item.put("runtimeLabel", "inproc".equals(descriptor.runtimeKind().value()) ? "Java 内置" : "外部适配器");
         item.put("kindLabel", "工具");
         item.put("migration_status", descriptor.runtimeKind().value().equals("inproc")
                 ? "java_migrated" : "http_adapter_pending");
         item.put("enabled", "active".equalsIgnoreCase(descriptor.status()));
         item.put("statusLabel", "active".equalsIgnoreCase(descriptor.status()) ? "可用" : "已停用");
         item.put("status", descriptor.status());
         item.put("usageCount", 0);
         item.put("technology", "Java Tool / CommAND Runtime");
        item.put("hidden", false);
        item.put("category", category(descriptor.key().id()));
        item.put("subcategory", descriptor.key().id().split("\\.")[0]);
        item.put("manifest", frontendManifest(manifest));
        return item;
    }

    private Map<String, Object> workflowSummary(DefinitionDocument definition) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", definition.key().id());
         item.put("name", displayName(definition.key().id(), firstText(definition.content(), "title", definition.key().id())));
         item.put("description", firstText(definition.content(), "description", "可执行工作流"));
         item.put("purpose", firstText(definition.content(), "description", "按固定步骤编排多个工具，形成可追踪的业务流程。"));
         item.put("principle", "Workflow 冻结版本与步骤输入映射，由 Scheduler 顺序推进并保存每个节点的输入、输出和事件。");
        item.put("version", String.valueOf(definition.key().version()));
         item.put("kind", "workflow");
         item.put("kindLabel", "工作流");
         item.put("runtime_kind", "pipeline");
         item.put("runtimeLabel", "Java 流程");
         item.put("technology", "Java Workflow / Hibernate / Scheduler");
         item.put("usageCount", 0);
        item.put("migration_status", "java_migrated");
         item.put("enabled", true);
         item.put("status", "active");
         item.put("statusLabel", "可用");
        item.put("runnable", true);
        Object pipelineRef = definition.content().get("capability_pipeline_ref");
        Object pipelineVersion = pipelineRef instanceof Map<?, ?> ref && ref.get("version") != null
                ? ref.get("version") : 1;
        List<Map<String, Object>> steps = pipelineRef instanceof Map<?, ?> ref
                ? pipelineSteps(String.valueOf(ref.get("id")), ((Number) pipelineVersion).intValue())
                : List.of();
         item.put("steps", steps.isEmpty() ? 1 : steps.size());
         item.put("stepsLabel", (steps.isEmpty() ? 1 : steps.size()) + " 个步骤");
         item.put("dependencies", steps);
        return item;
    }

    private List<Map<String, Object>> pipelineSteps(String id, int version) {
        DefinitionDocument pipeline;
        try {
            pipeline = definitions.get(new com.zthcpa.command.contract.DefinitionKey(
                    DefinitionKind.CAPABILITY_PIPELINE, id, version));
        } catch (RuntimeException ignored) {
            return List.of();
        }
        Object raw = pipeline.content().get("steps");
        if (!(raw instanceof List<?> list)) return List.of();
        return list.stream().filter(Map.class::isInstance).map(value -> {
            Map<?, ?> step = (Map<?, ?>) value;
            Object ref = step.get("definition_ref");
            if (ref instanceof Map<?, ?> tool) {
                return Map.of("id", String.valueOf(tool.get("id")), "version", tool.get("version"), "step", step.get("id"));
            }
            return Map.of("step", step.get("id"));
        }).toList();
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

    private static Map<String, Object> studioView(String id, String title, String type, String icon,
                                                   boolean defaultView, Map<String, Object> props) {
        return Map.of("id", id, "title", title, "type", type, "icon", icon, "default", defaultView, "props", props);
    }

    private static Map<String, Object> page(String id, String title, String framework, String icon,
                                            boolean defaultPage, List<Map<String, Object>> components) {
        return Map.of("id", id, "title", title, "framework", framework, "icon", icon,
                "default", defaultPage, "navigation", Map.of("kind", "tab", "group", "command"),
                "components", components);
    }

    private static Map<String, Object> component(String id, String type, String region,
                                                 Map<String, Object> props) {
        return component(id, type, region, props, null);
    }

    private static Map<String, Object> component(String id, String type, String region,
                                                 Map<String, Object> props, String resource) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("type", type);
        result.put("region", region);
        result.put("props", props);
        if (resource != null) result.put("data", Map.of("resource", resource));
        return result;
    }

    private static Map<String, Object> resource(String id, String name, String path) {
        return Map.of("id", id, "name", name, "description", name, "actions", List.of(path));
    }

    private static Map<String, Object> action(String id, String name, String method, String path) {
        return Map.of("id", id, "name", name, "method", method, "path", path);
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

    private static String displayName(String id, String fallback) {
        return switch (id) {
            case "ocr.extract-document" -> "OCR 文档提取";
            case "translate.text" -> "文本翻译";
            case "ocr.extract-by-template" -> "按模板提取 OCR 结果";
            case "llm.chat.complete" -> "文本模型对话";
            case "llm.chat.complete-json" -> "结构化模型提取";
            case "file.inspect" -> "文件信息检查";
            case "pdf.extract.pages" -> "PDF 文本页提取";
            case "pdf.pages.to.images" -> "PDF 页面转图片";
            case "ocr.vision.extract" -> "图片视觉识别";
            case "ocrdb.write.records" -> "保存 OCR 记录";
            case "ocrdb.extract.units" -> "提取 OCR 文本单元";
            case "spec.template.resolve" -> "解析识别模板";
            case "records.view.query" -> "查询识别结果视图";
            case "records.export.xlsx" -> "导出 Excel 结果";
            case "records.export.csv" -> "导出 CSV 结果";
            case "records.merge.crosspage" -> "合并跨页记录";
            case "text.dedup.values" -> "文本去重";
            case "text.verify.fidelity" -> "文本保真检查";
            case "txt.extract.text" -> "提取文本文件内容";
            case "table.classify.columns" -> "识别表格列类型";
            case "image.transform" -> "图片翻转";
            default -> containsCjk(fallback) ? fallback : id;
        };
    }

    private static String purpose(String id, String fallback) {
        return switch (id) {
            case "file.inspect" -> "检查受控文件的名称、格式、大小和摘要值，为后续文件处理提供可信元数据。";
            case "pdf.extract.pages" -> "提取 PDF 各页的文字内容，并标记需要视觉识别的扫描页。";
            case "pdf.pages.to.images" -> "将 PDF 页面渲染为图片，供 OCR 和图像处理工作流逐页使用。";
            case "ocr.vision.extract" -> "识别图片中的文字与字段，输出可继续查询和导出的结构化记录。";
            case "ocrdb.write.records" -> "将 OCR 识别结果写入 CommAND 结果库，供视图查询、复核和导出。";
            case "ocrdb.extract.units" -> "把 OCR 记录整理为文本段和表格单元，供后续处理步骤消费。";
            case "spec.template.resolve" -> "解析并规范化识别模板，生成后续 OCR 步骤使用的字段定义。";
            case "records.view.query" -> "按视图规则筛选、排序和组织持久化的 OCR 记录。";
            case "records.export.xlsx" -> "将结构化记录生成可下载的 Excel 工作簿。";
            case "records.export.csv" -> "将结构化记录生成通用 CSV 文件。";
            case "records.merge.crosspage" -> "合并跨页重复或连续的记录，保留字段关联与原始顺序。";
            case "text.dedup.values" -> "清理重复文本值并保留原值到去重结果的索引关系。";
            case "text.verify.fidelity" -> "检查文本转换前后的数字、占位符和关键内容是否保持一致。";
            case "txt.extract.text" -> "读取受控文本文件并输出文本内容与文件摘要。";
            case "table.classify.columns" -> "根据表格样例识别列的数据类型和处理方式。";
            case "llm.chat.complete" -> "使用配置的大模型对话接口生成文本结果。";
            case "llm.chat.complete-json" -> "调用大模型并按 JSON 对象格式返回结构化结果。";
            case "image.transform" -> "对受控图片执行水平或垂直翻转，并生成可预览的 PNG 结果。";
            default -> containsCjk(fallback) ? fallback : "提供可复用的原子处理能力。";
        };
    }

    private static boolean containsCjk(String value) {
        return value != null && value.codePoints().anyMatch(code -> code >= 0x3400 && code <= 0x9fff);
    }
}
