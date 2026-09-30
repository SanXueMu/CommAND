package com.zthcpa.command.tools.pdf;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.pdmodel.PDDocument;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Extracts text units from text PDFs and marks image-only pages for the vision adapter. */
public final class PdfExtractPagesTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("pdf.extract.pages", 1);
    private final Path dataDirectory;

    public PdfExtractPagesTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public PdfExtractPagesTool(Path dataDirectory) { this.dataDirectory = dataDirectory.toAbsolutePath().normalize(); }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path file = resolve(required(input.get("file"), "file"));
        if (!file.startsWith(dataDirectory) || !Files.isRegularFile(file)) throw new IllegalArgumentException("file must be a readable data file");
        int minChars = input.get("min_chars_per_page") == null ? 20 : Integer.parseInt(String.valueOf(input.get("min_chars_per_page")));
        try (PDDocument document = Loader.loadPDF(file.toFile())) {
            PDFTextStripper stripper = new PDFTextStripper();
            List<Map<String, Object>> units = new ArrayList<>();
            for (int page = 1; page <= document.getNumberOfPages(); page++) {
                stripper.setStartPage(page);
                stripper.setEndPage(page);
                String text = stripper.getText(document).strip();
                Map<String, Object> unit = new LinkedHashMap<>();
                unit.put("unit_id", file.getFileName() + "#page-" + page);
                unit.put("unit_type", "text");
                unit.put("page", page);
                unit.put("text", text);
                unit.put("meta", Map.of("no_text", text.length() < minChars));
                units.add(unit);
                progress.emit(Map.of("type", "progress", "phase", "page_extracted", "page", page, "pages_total", document.getNumberOfPages()));
            }
            return Map.of("file", file.toString(), "file_hash", sha256(file), "kind", "pdf", "units", units, "pages_total", document.getNumberOfPages());
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to extract PDF pages: " + file, exception);
        }
    }

    private static String required(Object value, String name) { if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(name + " must not be blank"); return String.valueOf(value); }
    private Path resolve(String raw) {
        Path supplied = Path.of(raw);
        return (supplied.isAbsolute() ? supplied : dataDirectory.resolve(supplied)).toAbsolutePath().normalize();
    }
    private static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(Files.readAllBytes(file));
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception exception) { throw new IllegalStateException("Unable to hash PDF", exception); }
    }
}
