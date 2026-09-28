package com.zthcpa.command.tools.ocr;

import java.util.List;
import java.util.Map;

public interface VisionClient {
    VisionResponse extract(String model, String instruction, String mediaType, String base64Data);

    record VisionResponse(String content, String model, Map<String, Object> usage) {
        public VisionResponse {
            if (content == null || model == null || model.isBlank()) throw new IllegalArgumentException("Vision response is invalid");
            usage = usage == null ? Map.of() : Map.copyOf(usage);
        }
    }
}
