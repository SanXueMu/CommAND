package com.zthcpa.command.tools.txt;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Extracts a UTF-8 text file into one text unit. */
public final class TxtExtractTextTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("txt.extract.text", 1);

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Object fileValue = input.get("file");
        if (fileValue == null || String.valueOf(fileValue).isBlank()) {
            throw new IllegalArgumentException("file must not be blank");
        }

        Path path = Path.of(String.valueOf(fileValue));
        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException("File does not exist: " + path);
        }

        try {
            String text = Files.readString(path, StandardCharsets.UTF_8).trim();
            String hash = sha256(path);
            Map<String, Object> unit = new LinkedHashMap<>();
            unit.put("unit_id", path.getFileName().toString());
            unit.put("unit_type", "text");
            unit.put("text", text);

            progress.emit(Map.of("type", "progress", "phase", "extracted", "chars", text.length()));
            return Map.of(
                    "file", path.toString(),
                    "file_hash", hash,
                    "kind", "text",
                    "units", List.of(unit)
            );
        } catch (IOException exception) {
            throw new IllegalArgumentException("Unable to read file: " + path, exception);
        }
    }

    private String sha256(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(Files.readAllBytes(path));
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
