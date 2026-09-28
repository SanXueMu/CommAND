package com.zthcpa.command.configuration.tool;

import com.zthcpa.command.tools.records.MergeCrosspageTool;
import com.zthcpa.command.tools.records.ExportCsvTool;
import com.zthcpa.command.tools.table.ClassifyColumnsTool;
import com.zthcpa.command.tools.text.DedupValuesTool;
import com.zthcpa.command.tools.text.VerifyFidelityTool;
import com.zthcpa.command.tools.txt.TxtExtractTextTool;
import com.zthcpa.command.tools.text.TranslateTextTool;
import com.zthcpa.command.tools.ocr.OcrTemplateResolveTool;
import com.zthcpa.command.tools.ocr.OcrExtractUnitsTool;
import com.zthcpa.command.tools.ocr.OcrWriteRecordsTool;
import com.zthcpa.command.tools.ocr.RecordsViewQueryTool;
import com.zthcpa.command.tools.file.FileInspectTool;
import com.zthcpa.command.tools.pdf.PdfExtractPagesTool;
import com.zthcpa.command.tools.pdf.PdfPagesToImagesTool;
import com.zthcpa.command.tools.records.RecordsExportXlsxTool;
import com.zthcpa.command.persistence.ocr.OcrPersistenceService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PureDataToolConfiguration {
    @Bean
    MergeCrosspageTool mergeCrosspageTool() {
        return new MergeCrosspageTool();
    }

    @Bean
    ExportCsvTool exportCsvTool() {
        return new ExportCsvTool();
    }

    @Bean
    DedupValuesTool dedupValuesTool() {
        return new DedupValuesTool();
    }

    @Bean
    VerifyFidelityTool verifyFidelityTool() {
        return new VerifyFidelityTool();
    }

    @Bean
    TxtExtractTextTool txtExtractTextTool() {
        return new TxtExtractTextTool();
    }

    @Bean
    ClassifyColumnsTool classifyColumnsTool() {
        return new ClassifyColumnsTool();
    }

    @Bean
    @org.springframework.boot.autoconfigure.condition.ConditionalOnBean(com.zthcpa.command.tools.llm.LlmClient.class)
    TranslateTextTool translateTextTool(com.zthcpa.command.tools.llm.LlmClient client) {
        return new TranslateTextTool(client);
    }

    @Bean
    OcrTemplateResolveTool ocrTemplateResolveTool() { return new OcrTemplateResolveTool(); }

    @Bean
    OcrExtractUnitsTool ocrExtractUnitsTool() { return new OcrExtractUnitsTool(); }

    @Bean
    OcrWriteRecordsTool ocrWriteRecordsTool(OcrPersistenceService store) { return new OcrWriteRecordsTool(store); }

    @Bean
    RecordsViewQueryTool recordsViewQueryTool() { return new RecordsViewQueryTool(); }

    @Bean
    FileInspectTool fileInspectTool() { return new FileInspectTool(); }

    @Bean
    PdfExtractPagesTool pdfExtractPagesTool() { return new PdfExtractPagesTool(); }

    @Bean
    PdfPagesToImagesTool pdfPagesToImagesTool() { return new PdfPagesToImagesTool(); }

    @Bean
    RecordsExportXlsxTool recordsExportXlsxTool() { return new RecordsExportXlsxTool(); }
}
