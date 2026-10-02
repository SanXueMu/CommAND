package com.zthcpa.command.tools.xlsx;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Extracts formatted XLSX cell values while preserving sheet and cell coordinates. */
public final class XlsxExtractValuesTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("xlsx.extract.values", 1);
    private final Path dataDirectory;

    public XlsxExtractValuesTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public XlsxExtractValuesTool(Path dataDirectory) { this.dataDirectory = dataDirectory.toAbsolutePath().normalize(); }

    @Override public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path path = resolve(input.get("file"));
        DataFormatter formatter = new DataFormatter();
        List<Map<String, Object>> sheets = new ArrayList<>();
        int totalRows = 0;
        try (InputStream stream = Files.newInputStream(path); Workbook workbook = new XSSFWorkbook(stream)) {
            for (int sheetIndex = 0; sheetIndex < workbook.getNumberOfSheets(); sheetIndex++) {
                var sheet = workbook.getSheetAt(sheetIndex);
                List<Map<String, Object>> rows = new ArrayList<>();
                for (Row row : sheet) {
                    List<Map<String, Object>> cells = new ArrayList<>();
                    for (int column = row.getFirstCellNum(); column >= 0 && column <= row.getLastCellNum(); column++) {
                        var cell = row.getCell(column, Row.MissingCellPolicy.RETURN_BLANK_AS_NULL);
                        if (cell == null) continue;
                        String value = formatter.formatCellValue(cell);
                        if (value.isBlank()) continue;
                        cells.add(Map.of("column", column, "value", value, "type", cell.getCellType().name().toLowerCase()));
                    }
                    if (!cells.isEmpty()) {
                        rows.add(Map.of("row", row.getRowNum(), "cells", cells));
                        totalRows++;
                    }
                }
                sheets.add(Map.of("index", sheetIndex, "name", sheet.getSheetName(), "rows", rows));
                progress.emit(Map.of("type", "progress", "phase", "sheet_extracted", "sheet", sheetIndex + 1, "sheets_total", workbook.getNumberOfSheets()));
            }
            return Map.of("file", path.toString(), "file_hash", sha256(path), "kind", "xlsx", "sheets", sheets, "rows", totalRows);
        } catch (IOException exception) {
            throw new IllegalArgumentException("Unable to read XLSX file: " + path, exception);
        }
    }

    private Path resolve(Object value) {
        if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException("file must not be blank");
        Path supplied = Path.of(String.valueOf(value));
        Path path = (supplied.isAbsolute() ? supplied : dataDirectory.resolve(supplied)).toAbsolutePath().normalize();
        if (!path.startsWith(dataDirectory)) throw new IllegalArgumentException("file must be inside COMMAND_DATA_DIR");
        if (!Files.isRegularFile(path)) throw new IllegalArgumentException("File does not exist: " + path);
        return path;
    }

    private static String sha256(Path path) throws IOException {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))); }
        catch (Exception exception) { throw new IllegalStateException("SHA-256 is unavailable", exception); }
    }
}
