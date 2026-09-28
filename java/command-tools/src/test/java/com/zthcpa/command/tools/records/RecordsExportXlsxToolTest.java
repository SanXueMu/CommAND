package com.zthcpa.command.tools.records;

import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecordsExportXlsxToolTest {
    @Test
    void writesRealXlsxWithHeadersAndRows() throws Exception {
        Path data = Files.createTempDirectory("command-xlsx-");
        try {
            Map<String, Object> output = new RecordsExportXlsxTool(data).execute(Map.of(
                    "name", "ocr-result",
                    "columns", List.of("编号", "金额"),
                    "rows", List.of(Map.of("编号", "A-1", "金额", "12.50"))
            ), event -> { });
            Path file = Path.of(String.valueOf(output.get("file")));
            assertTrue(Files.isRegularFile(file));
            try (var workbook = WorkbookFactory.create(file.toFile())) {
                assertEquals("编号", workbook.getSheetAt(0).getRow(0).getCell(0).getStringCellValue());
                assertEquals("A-1", workbook.getSheetAt(0).getRow(1).getCell(0).getStringCellValue());
            }
        } finally {
            Files.walk(data).sorted(java.util.Comparator.reverseOrder()).forEach(path -> path.toFile().delete());
        }
    }
}
