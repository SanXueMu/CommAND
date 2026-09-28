package com.zthcpa.command.tools.ocr;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/** Applies the portable subset of ViewSpec needed by the OCR workbench preview. */
public final class RecordsViewQueryTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("records.view.query", 1);

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Object raw = input.get("records");
        if (!(raw instanceof List<?> list)) throw new IllegalArgumentException("records must be an array");
        List<Map<String, Object>> records = list.stream().filter(Map.class::isInstance).map(item -> (Map<String, Object>) item).toList();
        Object specValue = input.get("view_spec");
        if (!(specValue instanceof Map<?, ?> spec)) throw new IllegalArgumentException("view_spec must be an object");
        List<String> columns = columns(spec.get("columns"), records);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> record : records) {
            Map<String, Object> row = new java.util.LinkedHashMap<>();
            for (String column : columns) row.put(column, record.getOrDefault(column, ""));
            rows.add(row);
        }
        progress.emit(Map.of("type", "progress", "phase", "view", "rows", rows.size()));
        Object viewName = spec.containsKey("name") ? spec.get("name") : "";
        return Map.of("columns", columns, "rows", rows, "splits", List.of(), "view_name", viewName);
    }

    private static List<String> columns(Object value, List<Map<String, Object>> records) {
        if (value instanceof List<?> list && !list.isEmpty()) return list.stream().map(String::valueOf).toList();
        LinkedHashSet<String> names = new LinkedHashSet<>();
        records.forEach(record -> names.addAll(record.keySet()));
        return List.copyOf(names);
    }
}
