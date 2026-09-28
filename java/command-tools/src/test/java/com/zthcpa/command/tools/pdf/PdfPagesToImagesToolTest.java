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
import static org.junit.jupiter.api.Assertions.assertTrue;

class PdfPagesToImagesToolTest {
    @Test
    void rendersPdfPageToControlledPngArtifact() throws Exception {
        Path data = Files.createTempDirectory("command-pdf-render-");
        Path pdf = data.resolve("sample.pdf");
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            try (PDPageContentStream content = new PDPageContentStream(document, document.getPage(0))) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 700);
                content.showText("render sample");
                content.endText();
            }
            document.save(pdf.toFile());
        }
        try {
            Map<String, Object> output = new PdfPagesToImagesTool(data).execute(Map.of("file", pdf.toString(), "dpi", 72), event -> { });
            assertEquals(1, output.get("pages_total"));
            Map<?, ?> page = (Map<?, ?>) ((List<?>) output.get("pages")).get(0);
            assertTrue(Files.isRegularFile(Path.of(String.valueOf(page.get("file")))));
            assertTrue((Integer) page.get("width") > 0);
            assertTrue(String.valueOf(page.get("sha256")).length() == 64);
        } finally {
            Files.walk(data).sorted(java.util.Comparator.reverseOrder()).forEach(path -> path.toFile().delete());
        }
    }
}
