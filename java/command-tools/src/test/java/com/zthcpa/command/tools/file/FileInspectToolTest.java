package com.zthcpa.command.tools.file;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FileInspectToolTest {
    @Test
    void returnsStableMetadataAndRejectsOutsideFile() throws Exception {
        Path data = Files.createTempDirectory("command-file-");
        Path file = data.resolve("upload.png");
        Files.write(file, new byte[]{1, 2, 3});
        try {
            Map<String, Object> output = new FileInspectTool(data).execute(Map.of("file", file.toString()), event -> { });
            assertEquals("upload.png", output.get("file_name"));
            assertEquals(3L, output.get("size_bytes"));
            assertEquals(MessageDigest.getInstance("SHA-256").digest(new byte[]{1, 2, 3}).length * 2, String.valueOf(output.get("sha256")).length());
            assertThrows(IllegalArgumentException.class, () -> new FileInspectTool(data).execute(Map.of("file", "/tmp/outside.png"), event -> { }));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(data);
        }
    }
}
