package com.zthcpa.command.tools.image;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

/** Controlled image transformation used by document and review workbenches. */
public final class ImageTransformTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("image.transform", 1);
    private final Path dataDirectory;

    public ImageTransformTool() { this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data"))); }

    public ImageTransformTool(Path dataDirectory) {
        this.dataDirectory = dataDirectory.toAbsolutePath().normalize();
    }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Path source = controlledFile(input.get("file"));
        String operation = String.valueOf(input.getOrDefault("operation", "flip_horizontal"));
        if (!operation.equals("flip_horizontal") && !operation.equals("flip_vertical")) {
            throw new IllegalArgumentException("operation must be flip_horizontal or flip_vertical");
        }
        try {
            BufferedImage original = ImageIO.read(source.toFile());
            if (original == null) throw new IllegalArgumentException("file is not a readable image");
            progress.emit(Map.of("type", "progress", "phase", "image_loaded", "width", original.getWidth(), "height", original.getHeight()));
            BufferedImage transformed = new BufferedImage(original.getWidth(), original.getHeight(), BufferedImage.TYPE_INT_ARGB);
            Graphics2D graphics = transformed.createGraphics();
            if (operation.equals("flip_horizontal")) {
                graphics.drawImage(original, original.getWidth(), 0, -original.getWidth(), original.getHeight(), null);
            } else {
                graphics.drawImage(original, 0, original.getHeight(), original.getWidth(), -original.getHeight(), null);
            }
            graphics.dispose();

            Path output = dataDirectory.resolve("outputs").resolve("image-transform")
                    .resolve(source.getFileName().toString().replaceFirst("(?i)\\.[^.]+$", "") + "-" + operation + ".png")
                    .normalize();
            if (!output.startsWith(dataDirectory)) throw new IllegalArgumentException("output path escapes data directory");
            Files.createDirectories(output.getParent());
            ImageIO.write(transformed, "png", output.toFile());
            progress.emit(Map.of("type", "progress", "phase", "image_written", "file", output.getFileName().toString()));
            return Map.of(
                    "kind", "image",
                    "media_type", "image/png",
                    "file", output.toString(),
                    "storage_key", dataDirectory.relativize(output).toString(),
                    "file_name", output.getFileName().toString(),
                    "operation", operation,
                    "width", transformed.getWidth(),
                    "height", transformed.getHeight(),
                    "sha256", sha256(output)
            );
        } catch (IOException exception) {
            throw new IllegalStateException("Unable to transform image: " + source, exception);
        }
    }

    private Path controlledFile(Object value) {
        if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException("file must not be blank");
        Path supplied = Path.of(String.valueOf(value));
        Path path = (supplied.isAbsolute() ? supplied : dataDirectory.resolve(supplied)).toAbsolutePath().normalize();
        if (!path.startsWith(dataDirectory) || !Files.isRegularFile(path)) {
            throw new IllegalArgumentException("file must be a readable data file");
        }
        return path;
    }

    private static String sha256(Path path) throws IOException {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        } catch (Exception exception) {
            throw new IOException("Unable to calculate image checksum", exception);
        }
    }
}
