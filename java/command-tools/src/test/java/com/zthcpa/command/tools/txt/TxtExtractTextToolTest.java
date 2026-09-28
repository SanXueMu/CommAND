package com.zthcpa.command.tools.txt;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TxtExtractTextToolTest {
    @Test
    void extractsTrimmedTextAndSha256IntoOneUnit() throws Exception {
        Path file = Files.createTempFile("command-text-", ".txt");
        try {
            Files.writeString(file, "  hello\nworld  ", StandardCharsets.UTF_8);
            Map<String, Object> output = new TxtExtractTextTool().execute(
                    Map.of("file", file.toString()), event -> { });

            assertEquals(file.toString(), output.get("file"));
            assertEquals(sha256("  hello\nworld  "), output.get("file_hash"));
            assertEquals("text", output.get("kind"));
            assertEquals(Map.of(
                    "unit_id", file.getFileName().toString(),
                    "unit_type", "text",
                    "text", "hello\nworld"
            ), ((List<?>) output.get("units")).get(0));
        } finally {
            assertTrue(Files.deleteIfExists(file));
        }
    }

    private String sha256(String value) throws Exception {
        return java.util.HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    }
}
