package com.zthcpa.command.tools.records;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Exports view rows as an Excel-friendly UTF-8 CSV file. */
public final class ExportCsvTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("records.export.csv", 1);

    private final Path dataDirectory;

    public ExportCsvTool() {
        this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data")));
    }

    public ExportCsvTool(Path dataDirectory) {
        this.dataDirectory = dataDirectory;
    }

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        List<?> rows = rows(input.get("rows"));
        List<String> columns = columns(input.get("columns"));
        String name = safeName(input.get("name"), "视图导出");
        Path outputDirectory = dataDirectory.resolve("outputs").resolve("exports");
        Path target = outputDirectory.resolve(name + ".csv");

        try {
            Files.createDirectories(outputDirectory);
            try (BufferedWriter writer = Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
                writer.write('\ufeff');
                writeRow(writer, columns);
                for (Object row : rows) {
                    List<Object> values = new ArrayList<>();
                    for (String column : columns) {
                        values.add(row instanceof Map<?, ?> map && map.containsKey(column) ? map.get(column) : "");
                    }
                    writeRow(writer, values);
                }
            }
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to export CSV: " + target, exception);
        }

        progress.emit(Map.of("type", "progress", "phase", "export",
                "message", "导出 " + rows.size() + " 行 → " + target.getFileName()));
        return Map.of("file", target.toString(), "rows_count", rows.size(), "columns", columns);
    }

    private List<?> rows(Object value) {
        if (!(value instanceof List<?> list)) {
            throw new IllegalArgumentException("rows must be an array");
        }
        return list;
    }

    private List<String> columns(Object value) {
        if (value == null) return List.of();
        if (!(value instanceof List<?> list)) {
            throw new IllegalArgumentException("columns must be an array");
        }
        return list.stream().map(String::valueOf).toList();
    }

    private String safeName(Object value, String fallback) {
        String name = value == null ? "" : String.valueOf(value).trim();
        name = name.replaceAll("[\\/:*?\"<>|]+", "_");
        return name.isBlank() ? fallback : name;
    }

    private void writeRow(BufferedWriter writer, List<?> values) throws IOException {
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) writer.write(',');
            writer.write(csvValue(values.get(index)));
        }
        writer.newLine();
    }

    private String csvValue(Object value) {
        String text = value == null ? "" : String.valueOf(value);
        if (text.contains(",") || text.contains("\"")) {
            return '"' + text.replace("\"", "\"\"") + '"';
        }
        return text;
    }
}
