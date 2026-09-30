package com.zthcpa.command.tools.file;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

/** Inspects a file within the configured data directory without exposing arbitrary host paths. */
public final class FileInspectTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("file.inspect", 1);
    private final Path dataDirectory;

    public FileInspectTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }

    public FileInspectTool(Path dataDirectory) {
        this.dataDirectory = dataDirectory.toAbsolutePath().normalize();
    }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        String rawPath = input.get("file") == null ? "" : String.valueOf(input.get("file"));
        if (rawPath.isBlank()) throw new IllegalArgumentException("file must not be blank");
        Path supplied = Path.of(rawPath);
        Path file = (supplied.isAbsolute() ? supplied : dataDirectory.resolve(supplied)).toAbsolutePath().normalize();
        if (!file.startsWith(dataDirectory)) throw new IllegalArgumentException("file must be inside COMMAND_DATA_DIR");
        if (!Files.isRegularFile(file)) throw new IllegalArgumentException("file does not exist: " + rawPath);
        try {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("file", file.toString());
            result.put("file_name", file.getFileName().toString());
            result.put("media_type", Files.probeContentType(file) == null ? "application/octet-stream" : Files.probeContentType(file));
            result.put("size_bytes", Files.size(file));
            result.put("sha256", sha256(file));
            result.put("kind", kind(result.get("media_type"), file));
            progress.emit(Map.of("type", "progress", "phase", "inspected", "file", file.getFileName().toString()));
            return result;
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to inspect file: " + file, exception);
        }
    }

    private static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) >= 0) if (read > 0) digest.update(buffer, 0, read);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private static String kind(Object mediaType, Path file) {
        String type = String.valueOf(mediaType);
        if (type.equals("application/pdf") || file.toString().toLowerCase().endsWith(".pdf")) return "pdf";
        if (type.startsWith("image/")) return "image";
        return "other";
    }
}
