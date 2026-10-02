package com.zthcpa.command.tools.xlsx;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.llm.LlmClient;
import com.zthcpa.command.tools.llm.LlmRequest;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/** Translates textual XLSX cells into a new controlled workbook while preserving workbook structure. */
public final class XlsxTranslateFileTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("xlsx.translate.file", 1);
    private final Path dataDirectory;
    private final LlmClient client;

    public XlsxTranslateFileTool(LlmClient client) { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data")), client); }
    public XlsxTranslateFileTool(Path dataDirectory, LlmClient client) {
        this.dataDirectory = dataDirectory.toAbsolutePath().normalize();
        this.client = client;
    }

    @Override public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path source = resolve(input.get("file"));
        String sourceLang = optional(input.get("source_lang"), "auto");
        String targetLang = required(input, "target_lang");
        String model = required(input, "model");
        String terms = optional(input.get("terms"), "");
        String name = sanitize(optional(input.get("name"), source.getFileName().toString().replaceFirst("(?i)\\.xlsx$", "")));
        Path output = dataDirectory.resolve("outputs").resolve("translations").resolve(name + "-translated.xlsx").normalize();
        if (!output.startsWith(dataDirectory)) throw new IllegalArgumentException("output path escapes data directory");
        int translated = 0;
        try (InputStream stream = Files.newInputStream(source); Workbook workbook = new XSSFWorkbook(stream)) {
            for (int sheetIndex = 0; sheetIndex < workbook.getNumberOfSheets(); sheetIndex++) {
                var sheet = workbook.getSheetAt(sheetIndex);
                for (var row : sheet) {
                    for (var cell : row) {
                        if (cell.getCellType() != CellType.STRING || cell.getStringCellValue().isBlank()) continue;
                        String text = cell.getStringCellValue();
                        String prompt = "Source language: " + sourceLang + "\nTarget language: " + targetLang
                                + (terms.isBlank() ? "" : "\nGlossary:\n" + terms)
                                + "\n\nTranslate only this spreadsheet cell value, preserving numbers and placeholders:\n" + text;
                        String translatedText = client.complete(new LlmRequest(model, List.of(
                                new LlmRequest.Message("system", "You are a professional translator. Return only the translated cell value."),
                                new LlmRequest.Message("user", prompt)), 0.2, null, false)).content();
                        cell.setCellValue(translatedText);
                        translated++;
                        progress.emit(Map.of("type", "progress", "phase", "cell_translated", "sheet", sheetIndex + 1, "row", row.getRowNum(), "column", cell.getColumnIndex(), "translated", translated));
                    }
                }
            }
            Files.createDirectories(output.getParent());
            try (OutputStream target = Files.newOutputStream(output)) { workbook.write(target); }
            return Map.of("file", output.toString(), "file_name", output.getFileName().toString(), "translated_cells", translated, "source_file", source.toString());
        } catch (Exception exception) {
            throw new IllegalStateException("Unable to translate XLSX file: " + source, exception);
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

    private static String required(Map<String, Object> input, String key) {
        String value = optional(input.get(key), "");
        if (value.isBlank()) throw new IllegalArgumentException(key + " must not be blank");
        return value;
    }

    private static String optional(Object value, String fallback) { return value == null ? fallback : String.valueOf(value); }
    private static String sanitize(String value) { String result = value.replaceAll("[^A-Za-z0-9._-]", "_"); return result.isBlank() ? "workbook" : result; }
}
