package com.zthcpa.command.tools.docx;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFTable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Extracts readable paragraph and table text from a controlled DOCX file. */
public final class DocxExtractTextTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("docx.extract.text", 1);
    private final Path dataDirectory;

    public DocxExtractTextTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public DocxExtractTextTool(Path dataDirectory) { this.dataDirectory = dataDirectory.toAbsolutePath().normalize(); }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path path = resolve(input.get("file"));
        try (InputStream stream = Files.newInputStream(path); XWPFDocument document = new XWPFDocument(stream)) {
            StringBuilder text = new StringBuilder();
            int units = 0;
            for (var body : document.getBodyElements()) {
                String value = body instanceof XWPFParagraph paragraph
                        ? paragraph.getText()
                        : body instanceof XWPFTable table ? table.getRows().stream()
                        .map(row -> row.getTableCells().stream().map(cell -> cell.getText().strip()).filter(cellText -> !cellText.isBlank()).reduce((left, right) -> left + " | " + right).orElse(""))
                        .filter(row -> !row.isBlank()).reduce((left, right) -> left + "\n" + right).orElse("")
                        : "";
                if (value != null && !value.isBlank()) {
                    if (text.length() > 0) text.append('\n');
                    text.append(value.strip());
                    units++;
                }
            }
            String extracted = text.toString().strip();
            Map<String, Object> unit = new LinkedHashMap<>();
            unit.put("unit_id", path.getFileName().toString());
            unit.put("unit_type", "text");
            unit.put("text", extracted);
            progress.emit(Map.of("type", "progress", "phase", "extracted", "units", units, "chars", extracted.length()));
            return Map.of("file", path.toString(), "file_hash", sha256(path), "kind", "docx", "units", List.of(unit));
        } catch (IOException exception) {
            throw new IllegalArgumentException("Unable to read DOCX file: " + path, exception);
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
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
