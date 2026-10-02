package com.zthcpa.command.tools.xlsx;

import com.zthcpa.command.tools.llm.LlmClient;
import com.zthcpa.command.tools.llm.LlmRequest;
import com.zthcpa.command.tools.llm.LlmResponse;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class XlsxTranslateFileToolTest {
    @Test
    void translatesTextCellsAndPreservesWorkbookStructure() throws Exception {
        Path data = Files.createTempDirectory("xlsx-translate");
        Path source = data.resolve("source.xlsx");
        try (XSSFWorkbook workbook = new XSSFWorkbook()) {
            var sheet = workbook.createSheet("表格");
            sheet.createRow(0).createCell(0).setCellValue("合同");
            sheet.getRow(0).createCell(1).setCellValue(42.0);
            sheet.getRow(0).createCell(2).setCellFormula("B1*2");
            try (var output = Files.newOutputStream(source)) { workbook.write(output); }
        }

        LlmClient fake = request -> new LlmResponse("译文", request.model(), Map.of());
        Map<String, Object> result = new XlsxTranslateFileTool(data, fake).execute(Map.of(
                "file", "source.xlsx", "target_lang", "English", "model", "fake-model"), event -> {});

        assertEquals(1, result.get("translated_cells"));
        Path translated = Path.of(String.valueOf(result.get("file")));
        assertTrue(Files.isRegularFile(translated));
        try (var input = Files.newInputStream(translated); XSSFWorkbook workbook = new XSSFWorkbook(input)) {
            var row = workbook.getSheet("表格").getRow(0);
            assertEquals("译文", row.getCell(0).getStringCellValue());
            assertEquals("42", new DataFormatter().formatCellValue(row.getCell(1)));
            assertEquals("B1*2", row.getCell(2).getCellFormula());
        }
    }
}
