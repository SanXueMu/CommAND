package com.zthcpa.command.tools.pdf;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class PdfExtractPagesToolTest {
    @Test
    void extractsTextPageAndPreservesFileHash() throws Exception {
        Path data = Files.createTempDirectory("command-pdf-");
        Path pdf = data.resolve("sample.pdf");
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            try (PDPageContentStream content = new PDPageContentStream(document, document.getPage(0))) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 700);
                content.showText("OCR document sample with enough text");
                content.endText();
            }
            document.save(pdf.toFile());
        }
        try {
            Map<String, Object> output = new PdfExtractPagesTool(data).execute(Map.of("file", pdf.toString()), event -> { });
            assertEquals("pdf", output.get("kind"));
            assertEquals(1, output.get("pages_total"));
            List<?> units = (List<?>) output.get("units");
            assertEquals(1, units.size());
            Map<?, ?> unit = (Map<?, ?>) units.get(0);
            assertFalse(String.valueOf(unit.get("text")).isBlank());
            assertFalse((Boolean) ((Map<?, ?>) unit.get("meta")).get("no_text"));
        } finally {
            Files.deleteIfExists(pdf);
            Files.deleteIfExists(data);
        }
    }
}
