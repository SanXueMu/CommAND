package com.zthcpa.command.tools.records;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExportCsvToolTest {
    @Test
    void writesUtf8BomCsvWithEscapedValuesAndSafeName() throws Exception {
        Path dataDirectory = Files.createTempDirectory("command-csv-");
        Map<String, Object> output = new ExportCsvTool(dataDirectory).execute(Map.of(
                "columns", List.of("部门", "备注"),
                "rows", List.of(Map.of("部门", "审计部", "备注", "含,逗号"),
                        Map.of("部门", "财务部", "备注", "含\"引号")),
                "name", "客户/明细"), event -> { });

        Path target = Path.of((String) output.get("file"));
        byte[] bytes = Files.readAllBytes(target);
        String text = new String(bytes, StandardCharsets.UTF_8);
        assertEquals(2, output.get("rows_count"));
        assertTrue(text.startsWith("\ufeff部门,备注\n"));
        assertTrue(text.contains("审计部,\"含,逗号\""));
        assertTrue(text.contains("财务部,\"含\"\"引号\""));
        assertTrue(target.getFileName().toString().equals("客户_明细.csv"));
    }
}
