package com.zthcpa.command.tools;

import java.util.Map;

public final class TextLlmTranslateJavaTool implements JavaTool {
    private final TextLlmTranslateTool delegate;

    public TextLlmTranslateJavaTool(TranslationModel model, TranslationCache cache) {
        this.delegate = new TextLlmTranslateTool(model, cache);
    }

    @Override
    public String id() {
        return TextLlmTranslateTool.ID;
    }

    @Override
    public int version() {
        return 1;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        return delegate.execute(input, progress).asMap();
    }
}
