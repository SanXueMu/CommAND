package com.zthcpa.command.contract;

import java.util.List;
import java.util.Map;

public interface OcrResultStore {
    String save(String sourcePath, String sourceHash, String templateId, int templateVersion, List<Map<String, Object>> records);
}
