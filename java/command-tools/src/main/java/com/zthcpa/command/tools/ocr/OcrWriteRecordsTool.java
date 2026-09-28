package com.zthcpa.command.tools.ocr;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/** Writes OCR records to a JSON result artifact during the first storage migration batch. */
public final class OcrWriteRecordsTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("ocrdb.write.records", 1);
    private final Path dataDirectory;
    private final ObjectMapper objectMapper;

    public OcrWriteRecordsTool(ObjectMapper objectMapper) { this(objectMapper, Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public OcrWriteRecordsTool(ObjectMapper objectMapper, Path dataDirectory) { this.objectMapper = objectMapper; this.dataDirectory = dataDirectory; }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Object raw = input.get("records");
        if (!(raw instanceof List<?> records) || records.isEmpty()) throw new IllegalArgumentException("records must be a non-empty array");
        String fileName = String.valueOf(input.getOrDefault("name", "ocr-results.json"));
        if (!fileName.matches("[A-Za-z0-9._-]+")) throw new IllegalArgumentException("name contains unsupported characters");
        Path output = dataDirectory.resolve("outputs").resolve("ocr").resolve(fileName).normalize();
        if (!output.startsWith(dataDirectory.toAbsolutePath().normalize()) && !output.startsWith(dataDirectory.normalize())) throw new IllegalArgumentException("output path escapes data directory");
        try {
            Files.createDirectories(output.getParent());
            objectMapper.writeValue(output.toFile(), Map.of("records", records, "source_path", input.getOrDefault("source_path", "records")));
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to write OCR result artifact", exception);
        }
        progress.emit(Map.of("type", "progress", "phase", "write", "written", records.size(), "file", output.toString()));
        return Map.of("file", output.toString(), "written", records.size(), "records", records);
    }
}
