package com.zthcpa.command.tools.pdf;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.apache.pdfbox.pdmodel.PDDocument;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Renders controlled PDF pages to PNG artifacts for the vision OCR Tool. */
public final class PdfPagesToImagesTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("pdf.pages.to.images", 1);
    private final Path dataDirectory;

    public PdfPagesToImagesTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }
    public PdfPagesToImagesTool(Path dataDirectory) { this.dataDirectory = dataDirectory.toAbsolutePath().normalize(); }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path file = Path.of(required(input.get("file"), "file")).toAbsolutePath().normalize();
        if (!file.startsWith(dataDirectory) || !Files.isRegularFile(file)) throw new IllegalArgumentException("file must be a readable data file");
        int dpi = input.get("dpi") == null ? 144 : Integer.parseInt(String.valueOf(input.get("dpi")));
        if (dpi < 36 || dpi > 300) throw new IllegalArgumentException("dpi must be between 36 and 300");
        Path outputDirectory = dataDirectory.resolve("outputs").resolve("pdf-pages").resolve(stem(file));
        try (PDDocument document = Loader.loadPDF(file.toFile())) {
            Files.createDirectories(outputDirectory);
            PDFRenderer renderer = new PDFRenderer(document);
            List<Map<String, Object>> pages = new ArrayList<>();
            for (int index = 0; index < document.getNumberOfPages(); index++) {
                BufferedImage image = renderer.renderImageWithDPI(index, dpi, ImageType.RGB);
                Path output = outputDirectory.resolve(String.format("page-%04d.png", index + 1));
                ImageIO.write(image, "png", output.toFile());
                Map<String, Object> page = new LinkedHashMap<>();
                page.put("page", index + 1);
                page.put("file", output.toString());
                page.put("width", image.getWidth());
                page.put("height", image.getHeight());
                page.put("sha256", sha256(output));
                pages.add(page);
                progress.emit(Map.of("type", "progress", "phase", "page_rendered", "page", index + 1, "pages_total", document.getNumberOfPages()));
            }
            return Map.of("file", file.toString(), "pages", pages, "pages_total", pages.size(), "dpi", dpi);
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to render PDF pages: " + file, exception);
        }
    }

    private static String stem(Path file) { String name = file.getFileName().toString(); int dot = name.lastIndexOf('.'); return dot > 0 ? name.substring(0, dot).replaceAll("[^A-Za-z0-9._-]", "_") : name; }
    private static String required(Object value, String name) { if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(name + " must not be blank"); return String.valueOf(value); }
    private static String sha256(Path file) throws IOException { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file))); } catch (Exception exception) { throw new IllegalStateException("Unable to hash rendered page", exception); } }
}
