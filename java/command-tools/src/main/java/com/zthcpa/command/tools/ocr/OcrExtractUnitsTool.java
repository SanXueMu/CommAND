package com.zthcpa.command.tools.ocr;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Converts persisted OCR records into translatable table and long-text units. */
public final class OcrExtractUnitsTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("ocrdb.extract.units", 1);

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        List<Map<String, Object>> records = records(input.get("records"));
        int threshold = input.get("long_value_chars") == null ? 200 : Integer.parseInt(String.valueOf(input.get("long_value_chars")));
        Map<String, Map<String, Object>> tables = new LinkedHashMap<>();
        List<Map<String, Object>> textUnits = new ArrayList<>();
        for (Map<String, Object> record : records) {
            String source = String.valueOf(record.getOrDefault("来源文件", record.getOrDefault("source_path", "records")));
            Map<String, Object> table = tables.computeIfAbsent(source, key -> {
                Map<String, Object> created = new LinkedHashMap<>();
                created.put("unit_id", key);
                created.put("unit_type", "table");
                created.put("rows", new ArrayList<>(List.of(List.of("字段 (页码)", "值"))));
                return created;
            });
            @SuppressWarnings("unchecked") List<List<Object>> rows = (List<List<Object>>) table.get("rows");
            Object page = record.getOrDefault("页码", record.getOrDefault("page_number", 1));
            rows.add(List.of(page, ""));
            for (Map.Entry<String, Object> entry : record.entrySet()) {
                if (entry.getKey().equals("页码") || entry.getKey().equals("page_number") || entry.getKey().equals("来源文件") || entry.getKey().equals("source_path")) continue;
                String text = entry.getValue() == null ? "" : String.valueOf(entry.getValue());
                if (text.length() > threshold) {
                    textUnits.add(Map.of("unit_id", source + "·" + entry.getKey() + "·p" + page, "unit_type", "text", "text", text));
                } else {
                    rows.add(List.of(entry.getKey() + " (p" + page + ")", text));
                }
            }
        }
        List<Object> units = new ArrayList<>(tables.values());
        units.addAll(textUnits);
        progress.emit(Map.of("type", "progress", "phase", "extracted", "units", units.size()));
        return Map.of("units", units, "records_count", records.size(), "units_count", units.size());
    }

    private static List<Map<String, Object>> records(Object value) {
        if (!(value instanceof List<?> list) || list.isEmpty()) throw new IllegalArgumentException("records must be a non-empty array");
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> map)) throw new IllegalArgumentException("records must contain objects");
            Map<String, Object> row = new LinkedHashMap<>();
            map.forEach((key, val) -> row.put(String.valueOf(key), val));
            result.add(row);
        }
        return result;
    }
}
