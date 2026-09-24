package com.zthcpa.command.tools;

import java.util.List;

public record TranslationOptions(
        String model,
        String fallbackModel,
        String sourceLanguage,
        String targetLanguage,
        List<Term> terms,
        boolean premium
) {
    public TranslationOptions {
        model = model == null || model.isBlank() ? "qwen-mt-flash" : model;
        fallbackModel = fallbackModel == null || fallbackModel.isBlank() ? "qwen3.7-flash" : fallbackModel;
        targetLanguage = targetLanguage == null || targetLanguage.isBlank() ? "Chinese" : targetLanguage;
        terms = List.copyOf(terms == null ? List.of() : terms);
    }

    public record Term(String source, String target) { }
}
