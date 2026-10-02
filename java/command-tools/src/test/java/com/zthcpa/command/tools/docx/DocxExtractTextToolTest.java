package com.zthcpa.command.tools.docx;

import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DocxExtractTextToolTest {
    @Test
    void extractsParagraphsAndTablesFromControlledDocx() throws Exception {
        Path data = Files.createTempDirectory("docx-tool");
        Path file = data.resolve("source.docx");
        try (XWPFDocument document = new XWPFDocument()) {
            document.createParagraph().createRun().setText("第一段");
            document.createTable(1, 1).getRow(0).getCell(0).setText("表格内容");
            try (var output = Files.newOutputStream(file)) { document.write(output); }
        }

        Map<String, Object> output = new DocxExtractTextTool(data).execute(Map.of("file", "source.docx"), event -> {});
        Map<?, ?> unit = (Map<?, ?>) ((java.util.List<?>) output.get("units")).get(0);
        assertEquals("docx", output.get("kind"));
        assertEquals("第一段\n表格内容", unit.get("text"));
    }

    @Test
    void rejectsPathOutsideDataDirectory() throws Exception {
        Path data = Files.createTempDirectory("docx-tool");
        assertThrows(IllegalArgumentException.class, () -> new DocxExtractTextTool(data).execute(Map.of("file", "../outside.docx"), event -> {}));
    }
}
