package com.zthcpa.command.tools.text;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DedupValuesToolTest {
    @Test
    void normalizesDatesBeforeDeduplicationAndKeepsOriginalMappings() {
        Map<String, Object> output = new DedupValuesTool().execute(Map.of(
                "segments", List.of("2023-11-16 报告", "2023-11-17 报告", "纯文本")
        ), e -> { });
        assertEquals(List.of("[[DATE_1]] 报告", "纯文本"), output.get("unique"));
        assertEquals(List.of(0, 0, 1), output.get("index_map"));
        assertEquals(Map.of("[[DATE_1]]", "2023-11-16"), ((List<?>) output.get("date_maps")).get(0));
        assertEquals(Map.of("[[DATE_1]]", "2023-11-17"), ((List<?>) output.get("date_maps")).get(1));
        assertEquals(Map.of(), ((List<?>) output.get("date_maps")).get(2));
    }
}
