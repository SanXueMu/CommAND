package com.zthcpa.command.tools.ocr;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OcrPureToolsTest {
    @Test
    void resolvesEnabledTemplateAndRejectsDisabledTemplate() {
        OcrTemplateResolveTool tool = new OcrTemplateResolveTool();
        Map<String, Object> template = new LinkedHashMap<>(Map.of(
                "id", "invoice",
                "prompt_template", "Extract {{fields}}",
                "fields", List.of("编号", "金额"),
                "enabled", true));
        Map<String, Object> output = tool.execute(Map.of("template", template), event -> { });
        assertEquals("Extract 编号, 金额", output.get("prompt"));
        template.put("enabled", false);
        assertThrows(IllegalArgumentException.class, () -> tool.execute(Map.of("template", template), event -> { }));
    }

    @Test
    void extractsTableAndLongTextUnits() {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("来源文件", "invoice.pdf");
        record.put("页码", 2);
        record.put("编号", "A-01");
        record.put("说明", "long-value");
        Map<String, Object> output = new OcrExtractUnitsTool().execute(
                Map.of("records", List.of(record), "long_value_chars", 4), event -> { });
        assertEquals(2, output.get("units_count"));
        List<?> units = (List<?>) output.get("units");
        assertEquals("table", ((Map<?, ?>) units.get(0)).get("unit_type"));
        assertEquals("text", ((Map<?, ?>) units.get(1)).get("unit_type"));
    }

    @Test
    void writesRecordsThroughResultStorePort() {
        Map<String, Object> output = new OcrWriteRecordsTool((sourcePath, sourceHash, templateId, templateVersion, records) -> "result-1").execute(
                Map.of("records", List.of(Map.of("页码", 1, "金额", "10"))), event -> { });
        assertEquals("result-1", output.get("result_set_id"));
        assertEquals(1, output.get("written"));
    }

    @Test
    void projectsRecordsUsingViewColumns() {
        Map<String, Object> output = new RecordsViewQueryTool().execute(Map.of(
                "records", List.of(Map.of("页码", 1, "编号", "A-01", "金额", "10")),
                "view_spec", Map.of("name", "摘要", "columns", List.of("编号", "金额"))), event -> { });
        assertEquals(List.of("编号", "金额"), output.get("columns"));
        assertEquals(List.of(Map.of("编号", "A-01", "金额", "10")), output.get("rows"));
    }
}
