package com.zthcpa.command.tools.records;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MergeCrosspageToolTest {
    @Test
    void joinsContinuationRowsAndFillsHeaders() {
        var tool = new MergeCrosspageTool();
        var input = List.of(
                Map.of("项目名称", "甲项目", "送审金额", "100", "页码", 1),
                Map.of("送审金额", "50", "页码", 2),
                Map.of("项目名称", "", "审定金额", "150", "页码", 3)
        );
        Map<String, Object> joined = tool.execute(Map.of("records", input, "key_field", "项目名称", "modes", List.of("join")), e -> { });
        assertEquals(1, joined.get("records_count"));
        assertEquals("100；50", ((List<Map<String, Object>>) joined.get("records")).get(0).get("送审金额"));

        Map<String, Object> filled = tool.execute(Map.of("records", input, "key_field", "项目名称", "modes", List.of("fill")), e -> { });
        assertEquals("甲项目", ((List<Map<String, Object>>) filled.get("records")).get(2).get("项目名称"));
    }
}
