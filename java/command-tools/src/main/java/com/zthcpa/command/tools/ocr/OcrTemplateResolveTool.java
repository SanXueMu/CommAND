package com.zthcpa.command.tools.ocr;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Resolves an OCR template document into the execution-ready prompt contract. */
public final class OcrTemplateResolveTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("spec.template.resolve", 1);

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Object raw = input.get("template");
        if (!(raw instanceof Map<?, ?> source)) {
            throw new IllegalArgumentException("template must be an object");
        }
        boolean enabled = !Boolean.FALSE.equals(source.get("enabled"));
        if (!enabled) throw new IllegalArgumentException("OCR template is disabled");
        String id = required(source.get("id"), "template.id");
        String prompt = required(source.get("prompt_template"), "template.prompt_template");
        List<String> fields = strings(source.get("fields"));
        String rendered = prompt.replace("{{fields}}", String.join(", ", fields));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("category", source.get("category"));
        result.put("prompt", rendered);
        result.put("fields", fields);
        result.put("hooks", source.get("hooks") instanceof List<?> hooks ? List.copyOf(hooks) : List.of());
        result.put("record_mode", source.get("record_mode"));
        result.put("lenient", Boolean.TRUE.equals(source.get("lenient")));
        result.put("view_spec", source.get("view_spec"));
        result.put("input_schema", source.get("input_schema"));
        progress.emit(Map.of("type", "progress", "phase", "template_resolved", "template_id", id));
        return result;
    }

    private static String required(Object value, String name) {
        if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(name + " must not be blank");
        return String.valueOf(value);
    }

    private static List<String> strings(Object value) {
        if (!(value instanceof List<?> list)) return new ArrayList<>();
        return list.stream().map(String::valueOf).toList();
    }
}
