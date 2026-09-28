package com.zthcpa.command.tools.ocr;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Extracts structured OCR records from one controlled image using a vision model. */
public final class VisionOcrTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("ocr.vision.extract", 1);
    private final VisionClient client;
    private final Path dataDirectory;
    private final ObjectMapper mapper;

    public VisionOcrTool(VisionClient client, ObjectMapper mapper) {
        this(client, mapper, Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data")));
    }

    public VisionOcrTool(VisionClient client, ObjectMapper mapper, Path dataDirectory) {
        this.client = client;
        this.mapper = mapper;
        this.dataDirectory = dataDirectory.toAbsolutePath().normalize();
    }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path file = Path.of(required(input.get("file"), "file")).toAbsolutePath().normalize();
        if (!file.startsWith(dataDirectory) || !Files.isRegularFile(file)) throw new IllegalArgumentException("file must be a readable data file");
        String mediaType = mediaType(file);
        if (!mediaType.startsWith("image/")) throw new IllegalArgumentException("ocr.vision.extract currently accepts image files only");
        String model = String.valueOf(input.getOrDefault("model", "qwen-vl-max"));
        List<String> fields = strings(input.get("fields"));
        String instruction = prompt(input, fields);
        progress.emit(Map.of("type", "progress", "phase", "vision_request", "file", file.getFileName().toString()));
        VisionClient.VisionResponse response;
        try {
            response = client.extract(model, instruction, mediaType, Base64.getEncoder().encodeToString(Files.readAllBytes(file)));
        } catch (Exception exception) {
            throw new IllegalStateException("Vision OCR failed: " + exception.getMessage(), exception);
        }
        List<Map<String, Object>> records = parseRecords(response.content());
        progress.emit(Map.of("type", "progress", "phase", "vision_completed", "records", records.size()));
        return Map.of("file", file.toString(), "model", response.model(), "records", records, "records_count", records.size(), "usage", response.usage());
    }

    private List<Map<String, Object>> parseRecords(String content) {
        try {
            var node = mapper.readTree(content);
            var records = node.isArray() ? node : node.path("records");
            if (!records.isArray()) throw new IllegalArgumentException("Vision output must contain a records array");
            return mapper.convertValue(records, mapper.getTypeFactory().constructCollectionType(List.class, Map.class));
        } catch (Exception exception) {
            throw new IllegalStateException("Vision output is not valid OCR JSON", exception);
        }
    }

    private static String prompt(Map<String, Object> input, List<String> fields) {
        String custom = input.get("prompt") == null ? "" : String.valueOf(input.get("prompt"));
        return (custom.isBlank() ? "Extract structured OCR records from this image." : custom)
                + " Return JSON with a records array. Fields: " + String.join(", ", fields);
    }

    private static List<String> strings(Object value) { return value instanceof List<?> list ? list.stream().map(String::valueOf).toList() : List.of(); }
    private static String required(Object value, String name) { if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(name + " must not be blank"); return String.valueOf(value); }
    private static String mediaType(Path file) { try { return Files.probeContentType(file) == null ? "application/octet-stream" : Files.probeContentType(file); } catch (Exception exception) { return "application/octet-stream"; } }
}
