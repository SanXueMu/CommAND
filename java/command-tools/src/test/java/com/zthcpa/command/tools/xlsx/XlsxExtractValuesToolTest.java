package com.zthcpa.command.tools.xlsx;

import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class XlsxExtractValuesToolTest {
    @Test
    void extractsNonEmptyCellsWithSheetAndCoordinates() throws Exception {
        Path data = Files.createTempDirectory("xlsx-tool");
        Path file = data.resolve("source.xlsx");
        try (XSSFWorkbook workbook = new XSSFWorkbook()) {
            var sheet = workbook.createSheet("合同");
            sheet.createRow(1).createCell(2).setCellValue("金额");
            sheet.getRow(1).createCell(3).setCellValue(1234.5);
            workbook.createSheet("空表");
            try (var output = Files.newOutputStream(file)) { workbook.write(output); }
        }

        Map<String, Object> output = new XlsxExtractValuesTool(data).execute(Map.of("file", "source.xlsx"), event -> {});
        var sheets = (java.util.List<?>) output.get("sheets");
        Map<?, ?> firstSheet = (Map<?, ?>) sheets.get(0);
        var rows = (java.util.List<?>) firstSheet.get("rows");
        Map<?, ?> row = (Map<?, ?>) rows.get(0);
        var cells = (java.util.List<?>) row.get("cells");
        assertEquals("xlsx", output.get("kind"));
        assertEquals(2, sheets.size());
        assertEquals(1, row.get("row"));
        assertEquals(2, ((Map<?, ?>) cells.get(0)).get("column"));
        assertEquals("金额", ((Map<?, ?>) cells.get(0)).get("value"));
        assertEquals("1234.5", ((Map<?, ?>) cells.get(1)).get("value"));
    }

    @Test
    void rejectsPathOutsideDataDirectory() throws Exception {
        Path data = Files.createTempDirectory("xlsx-tool");
        assertThrows(IllegalArgumentException.class, () -> new XlsxExtractValuesTool(data).execute(Map.of("file", "../outside.xlsx"), event -> {}));
    }
}
