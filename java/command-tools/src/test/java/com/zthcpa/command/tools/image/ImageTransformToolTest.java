package com.zthcpa.command.tools.image;

import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ImageTransformToolTest {
    @Test
    void flipsImageIntoControlledPngResult() throws Exception {
        Path data = Files.createTempDirectory("command-image-transform-");
        try {
            Path source = data.resolve("source.png");
            BufferedImage image = new BufferedImage(2, 1, BufferedImage.TYPE_INT_ARGB);
            image.setRGB(0, 0, Color.RED.getRGB());
            image.setRGB(1, 0, Color.BLUE.getRGB());
            ImageIO.write(image, "png", source.toFile());

            Map<String, Object> output = new ImageTransformTool(data).execute(
                    Map.of("file", "source.png", "operation", "flip_horizontal"), event -> { });
            Path result = Path.of(String.valueOf(output.get("file")));
            BufferedImage flipped = ImageIO.read(result.toFile());
            assertEquals("image", output.get("kind"));
            assertEquals(Color.BLUE.getRGB(), flipped.getRGB(0, 0));
            assertEquals(Color.RED.getRGB(), flipped.getRGB(1, 0));
            assertTrue(String.valueOf(output.get("storage_key")).startsWith("outputs/"));
        } finally {
            Files.walk(data).sorted(java.util.Comparator.reverseOrder()).forEach(path -> path.toFile().delete());
        }
    }
}
