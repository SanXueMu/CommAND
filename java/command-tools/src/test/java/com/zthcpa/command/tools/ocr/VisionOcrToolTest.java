package com.zthcpa.command.tools.ocr;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VisionOcrToolTest {
    @Test
    void sendsControlledImageToClientAndParsesRecords() throws Exception {
        Path data = Files.createTempDirectory("command-vision-");
        Path image = data.resolve("page.png");
        Files.write(image, new byte[]{1, 2, 3});
        RecordingVisionClient client = new RecordingVisionClient();
        try {
            Map<String, Object> output = new VisionOcrTool(client, new ObjectMapper(), data).execute(Map.of(
                    "file", image.toString(), "model", "vision-test", "fields", List.of("编号", "金额")), event -> { });
            assertEquals(1, output.get("records_count"));
            assertEquals("A-1", ((Map<?, ?>) ((List<?>) output.get("records")).get(0)).get("编号"));
            assertTrue(client.instruction.contains("编号"));
            assertEquals("image/png", client.mediaType);
            assertTrue(client.base64Data.length() > 0);
        } finally {
            Files.deleteIfExists(image);
            Files.deleteIfExists(data);
        }
    }

    private static final class RecordingVisionClient implements VisionClient {
        private String instruction;
        private String mediaType;
        private String base64Data;

        @Override
        public VisionResponse extract(String model, String instruction, String mediaType, String base64Data) {
            this.instruction = instruction;
            this.mediaType = mediaType;
            this.base64Data = base64Data;
            return new VisionResponse("{\"records\":[{\"编号\":\"A-1\"}]}", model, Map.of("total_tokens", 4));
        }
    }
}
