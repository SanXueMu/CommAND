package com.zthcpa.command.tools.text;

import com.zthcpa.command.tools.spi.ProgressSink;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class VerifyFidelityToolTest {
    private final VerifyFidelityTool tool = new VerifyFidelityTool();

    @Test
    void preservesVerificationReasonsAndProgress() {
        Map<String, Object> progress = new java.util.HashMap<>();
        Map<String, Object> result = tool.execute(Map.of(
                "sources", List.of("Invoice 2024 [[DATE_1]]", "2644", "hello world", "A long source " + "x".repeat(60)),
                "translations", List.of("发票 2024", "2645", "hello world", "短文")),
                progress::putAll);

        assertEquals(List.of("review", "review", "review", "review"), result.get("statuses"));
        assertEquals(List.of("missing_placeholder:[[DATE_1]]", "missing_number:2644", "untranslated", "truncated"),
                result.get("reasons"));
        assertEquals(Map.of("phase", "verified", "total", 4, "ok", 0), progress);
    }

    @Test
    void acceptsNumbersPlaceholdersAndEmptySourceWhenPreserved() {
        Map<String, Object> result = tool.execute(Map.of(
                "sources", List.of("Total 2024", "[[DATE_1]]", "   "),
                "translations", List.of("总计 2024", "[[DATE_1]]", "ignored")), event -> { });

        assertEquals(List.of("ok", "ok", "ok"), result.get("statuses"));
        assertEquals(List.of("", "", ""), result.get("reasons"));
        assertEquals(3, result.get("ok_count"));
    }

    @Test
    void rejectsMismatchedArrays() {
        assertThrows(IllegalArgumentException.class, () -> tool.execute(Map.of(
                "sources", List.of("a"), "translations", List.of()), event -> { }));
    }
}
