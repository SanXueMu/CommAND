package com.zthcpa.command.tools.ocr;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.contract.OcrResultStore;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.List;
import java.util.Map;

/** Persists OCR records through the storage port owned by the platform. */
public final class OcrWriteRecordsTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("ocrdb.write.records", 1);
    private final OcrResultStore store;

    public OcrWriteRecordsTool(OcrResultStore store) { this.store = store; }

    @Override
    public ToolKey key() { return KEY; }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        Object raw = input.get("records");
        if (!(raw instanceof List<?> records) || records.isEmpty()) throw new IllegalArgumentException("records must be a non-empty array");
        String resultSetId = store.save(String.valueOf(input.getOrDefault("source_path", "records")),
                input.get("source_hash") == null ? null : String.valueOf(input.get("source_hash")),
                input.get("template_id") == null ? null : String.valueOf(input.get("template_id")),
                Integer.parseInt(String.valueOf(input.getOrDefault("template_version", 1))),
                records.stream().map(item -> (Map<String, Object>) item).toList());
        progress.emit(Map.of("type", "progress", "phase", "write", "written", records.size(), "result_set_id", resultSetId));
        return Map.of("result_set_id", resultSetId, "written", records.size(), "records", records);
    }
}
