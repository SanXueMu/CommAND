package com.zthcpa.command.tools.table;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** Classifies table columns and harvests translatable segments deterministically. */
public final class ClassifyColumnsTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("table.classify.columns", 1);
    private static final Pattern DEFAULT_SKIP_PATTERN = Pattern.compile("^[\\d\\s/\\-:.,()%¥$€£#&+＋]+$");
    private static final Pattern HEADER_LETTER_PATTERN = Pattern.compile("[A-Za-z\\u4e00-\\u9fff]");

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        List<Map<String, Object>> units = units(input.get("units"));
        int enumMax = integer(input.get("enum_max"), 100);
        Pattern skipPattern = input.get("skip_pattern") == null
                ? DEFAULT_SKIP_PATTERN
                : Pattern.compile(String.valueOf(input.get("skip_pattern")));

        Map<String, List<Map<String, Object>>> classifications = new LinkedHashMap<>();
        List<String> segments = new ArrayList<>();
        List<Map<String, Object>> ranges = new ArrayList<>();
        Map<String, Map<String, Integer>> counts = new LinkedHashMap<>();

        for (Map<String, Object> unit : units) {
            String unitId = requiredText(unit.get("unit_id"), "unit_id");
            int start = segments.size();
            List<Map<String, Object>> classes = List.of();
            if ("table".equals(unit.get("unit_type"))) {
                List<List<String>> rows = rows(unit.get("rows"));
                classes = classify(rows, skipPattern, enumMax);
                classifications.put(unitId, classes);
                harvestTable(rows, classes, segments);
                counts.put(unitId, countClasses(classes));
            } else {
                String text = String.valueOf(unit.getOrDefault("text", "")).trim();
                if (!text.isEmpty()) segments.add(text);
            }
            ranges.add(Map.of("unit_id", unitId, "start", start, "count", segments.size() - start));
        }

        progress.emit(Map.of("type", "progress", "phase", "classified",
                "segments", segments.size(), "columns", counts));
        return Map.of("col_classes", classifications, "segments", segments, "ranges", ranges);
    }

    private List<Map<String, Object>> classify(List<List<String>> rows, Pattern skipPattern, int enumMax) {
        if (rows.isEmpty()) return List.of();
        int columns = rows.stream().mapToInt(List::size).max().orElse(0);
        List<Map<String, Object>> result = new ArrayList<>();
        for (int column = 0; column < columns; column++) {
            List<String> values = new ArrayList<>();
            for (int row = 1; row < rows.size(); row++) {
                if (column < rows.get(row).size() && !rows.get(row).get(column).trim().isEmpty()) {
                    values.add(rows.get(row).get(column));
                }
            }
            Set<String> unique = new LinkedHashSet<>(values);
            String classification = values.isEmpty() || values.stream().allMatch(value -> skipPattern.matcher(value).matches())
                    ? "skip" : unique.size() <= enumMax ? "enum" : "text";
            result.add(Map.of("col", column, "class", classification, "unique", unique.size()));
        }
        return result;
    }

    private void harvestTable(List<List<String>> rows, List<Map<String, Object>> classes, List<String> segments) {
        Set<Integer> translatable = new LinkedHashSet<>();
        for (Map<String, Object> column : classes) {
            if (!"skip".equals(column.get("class"))) translatable.add((Integer) column.get("col"));
        }
        if (rows.isEmpty()) return;
        for (int column = 0; column < rows.get(0).size(); column++) {
            String cell = rows.get(0).get(column);
            if (!cell.trim().isEmpty() && HEADER_LETTER_PATTERN.matcher(cell).find()) segments.add(cell.trim());
        }
        for (int row = 1; row < rows.size(); row++) {
            for (int column = 0; column < rows.get(row).size(); column++) {
                String cell = rows.get(row).get(column);
                if (translatable.contains(column) && !cell.trim().isEmpty()) segments.add(cell.trim());
            }
        }
    }

    private Map<String, Integer> countClasses(List<Map<String, Object>> classes) {
        Map<String, Integer> counts = new LinkedHashMap<>(Map.of("skip", 0, "enum", 0, "text", 0));
        for (Map<String, Object> item : classes) {
            String classification = String.valueOf(item.get("class"));
            counts.put(classification, counts.get(classification) + 1);
        }
        return counts;
    }

    private List<Map<String, Object>> units(Object value) {
        if (!(value instanceof List<?> list)) throw new IllegalArgumentException("units must be an array");
        return list.stream().map(item -> {
            if (!(item instanceof Map<?, ?> map)) throw new IllegalArgumentException("unit must be an object");
            Map<String, Object> unit = new LinkedHashMap<>();
            map.forEach((key, itemValue) -> unit.put(String.valueOf(key), itemValue));
            return unit;
        }).toList();
    }

    private List<List<String>> rows(Object value) {
        if (!(value instanceof List<?> list)) throw new IllegalArgumentException("rows must be an array");
        return list.stream().map(row -> {
            if (!(row instanceof List<?> cells)) throw new IllegalArgumentException("row must be an array");
            return cells.stream().map(String::valueOf).toList();
        }).toList();
    }

    private int integer(Object value, int fallback) {
        return value == null ? fallback : Integer.parseInt(String.valueOf(value));
    }

    private String requiredText(Object value, String field) {
        if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(field + " must not be blank");
        return String.valueOf(value);
    }
}
