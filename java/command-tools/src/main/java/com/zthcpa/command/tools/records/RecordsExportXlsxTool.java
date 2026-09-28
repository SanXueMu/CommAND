package com.zthcpa.command.tools.records;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public final class RecordsExportXlsxTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("records.export.xlsx", 1);
    private final Path dataDirectory;

    public RecordsExportXlsxTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public RecordsExportXlsxTool(Path dataDirectory) { this.dataDirectory = dataDirectory.toAbsolutePath().normalize(); }

    @Override public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        List<String> columns = strings(input.get("columns"));
        List<?> rows = input.get("rows") instanceof List<?> value ? value : List.of();
        String name = sanitize(String.valueOf(input.getOrDefault("name", "records")));
        Path output = dataDirectory.resolve("outputs").resolve("exports").resolve(name + ".xlsx").normalize();
        if (!output.startsWith(dataDirectory)) throw new IllegalArgumentException("output path escapes data directory");
        try {
            Files.createDirectories(output.getParent());
            try (Workbook workbook = new XSSFWorkbook(); OutputStream stream = Files.newOutputStream(output)) {
                var sheet = workbook.createSheet("records");
                Row header = sheet.createRow(0);
                for (int i = 0; i < columns.size(); i++) header.createCell(i).setCellValue(columns.get(i));
                for (int rowIndex = 0; rowIndex < rows.size(); rowIndex++) {
                    Row row = sheet.createRow(rowIndex + 1);
                    Object value = rows.get(rowIndex);
                    if (value instanceof Map<?, ?> map) {
                        for (int i = 0; i < columns.size(); i++) {
                            String column = columns.get(i);
                            Object cellValue = map.containsKey(column) ? map.get(column) : "";
                            row.createCell(i).setCellValue(String.valueOf(cellValue));
                        }
                    } else if (value instanceof List<?> list) {
                        for (int i = 0; i < list.size(); i++) row.createCell(i).setCellValue(String.valueOf(list.get(i)));
                    }
                    progress.emit(Map.of("type", "progress", "phase", "row_exported", "row", rowIndex + 1, "rows_total", rows.size()));
                }
                workbook.write(stream);
            }
            return Map.of("file", output.toString(), "file_name", output.getFileName().toString(), "rows", rows.size(), "columns", columns.size());
        } catch (Exception exception) { throw new IllegalStateException("Unable to export XLSX", exception); }
    }

    private static List<String> strings(Object value) { return value instanceof List<?> list ? list.stream().map(String::valueOf).toList() : List.of(); }
    private static String sanitize(String value) { String result = value.replaceAll("[^A-Za-z0-9._-]", "_"); return result.isBlank() ? "records" : result; }
}
