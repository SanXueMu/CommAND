package com.zthcpa.command.tools.records;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Pure record post-processing capability migrated from records.merge.crosspage. */
public final class MergeCrosspageTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("records.merge.crosspage", 1);
    private static final List<String> ABSENT = List.of("", "未见", "未出现");

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        List<Map<String, Object>> records = records(input.get("records"));
        String keyField = text(input.get("key_field"), "key_field");
        String separator = input.get("sep") == null || String.valueOf(input.get("sep")).isBlank()
                ? "；" : String.valueOf(input.get("sep"));
        List<String> modes = modes(input.get("modes"));
        List<Map<String, Object>> merged = records;
        for (String mode : modes) {
            merged = switch (mode) {
                case "join" -> join(merged, keyField, separator);
                case "fill" -> fill(merged, keyField);
                default -> throw new IllegalArgumentException("Unknown merge mode: " + mode);
            };
        }
        progress.emit(Map.of("type", "progress", "phase", "merge",
                "message", records.size() + " records -> " + merged.size() + " records (" + String.join(",", modes) + ")"));
        return Map.of("records", merged, "records_count", merged.size(),
                "merged_from", records.size(), "key_field", keyField);
    }

    private List<Map<String, Object>> join(List<Map<String, Object>> records, String keyField, String separator) {
        List<Map<String, Object>> output = new ArrayList<>();
        for (Map<String, Object> record : records) {
            Map<String, Object> row = new LinkedHashMap<>(record);
            if (!output.isEmpty() && isBlank(row.get(keyField))) {
                Map<String, Object> previous = output.get(output.size() - 1);
                row.forEach((field, value) -> {
                    if (field.equals("页码") || field.equals("行号") || field.equals(keyField)) return;
                    String text = String.valueOf(value == null ? "" : value).trim();
                    if (!text.isEmpty() && !ABSENT.contains(text)) {
                        String old = String.valueOf(previous.getOrDefault(field, ""));
                        previous.put(field, old.isEmpty() ? text : old + separator + text);
                    }
                });
            } else {
                output.add(row);
            }
        }
        return output;
    }

    private List<Map<String, Object>> fill(List<Map<String, Object>> records, String keyField) {
        List<Map<String, Object>> output = new ArrayList<>();
        String current = null;
        for (Map<String, Object> record : records) {
            Map<String, Object> row = new LinkedHashMap<>(record);
            String value = String.valueOf(row.getOrDefault(keyField, "")).trim();
            if (!value.isEmpty() && !ABSENT.contains(value)) current = value;
            else if (current != null) row.put(keyField, current);
            output.add(row);
        }
        return output;
    }

    private List<Map<String, Object>> records(Object value) {
        if (!(value instanceof List<?> list) || list.isEmpty()
                || list.stream().anyMatch(item -> !(item instanceof Map<?, ?>))) {
            throw new IllegalArgumentException("records must be a non-empty array of objects");
        }
        return list.stream().map(item -> {
            Map<String, Object> row = new LinkedHashMap<>();
            ((Map<?, ?>) item).forEach((key, itemValue) -> row.put(String.valueOf(key), itemValue));
            return row;
        }).toList();
    }

    private List<String> modes(Object value) {
        if (value == null) return List.of("join");
        if (!(value instanceof List<?> list)) throw new IllegalArgumentException("modes must be an array");
        return list.stream().map(item -> text(item, "mode")).toList();
    }

    private boolean isBlank(Object value) {
        return ABSENT.contains(String.valueOf(value == null ? "" : value).trim());
    }

    private String text(Object value, String field) {
        if (value == null || String.valueOf(value).isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return String.valueOf(value);
    }
}
