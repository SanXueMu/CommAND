package com.zthcpa.command.tools;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Pure Java implementation of the translation capability used by the clean runtime. */
public final class TextLlmTranslateTool {
    public static final String ID = "text.llm.translate";

    private final TranslationModel model;
    private final TranslationCache cache;

    public TextLlmTranslateTool(TranslationModel model, TranslationCache cache) {
        this.model = model;
        this.cache = cache;
    }

    public TranslationResult execute(Map<String, Object> input, ProgressSink progress) {
        List<String> segments = strings(input.get("segments"));
        TranslationOptions options = options(input);
        boolean useCache = !Boolean.FALSE.equals(input.get("use_cache"));
        Map<String, TranslationBatch.TranslationItem> results = new LinkedHashMap<>();
        List<String> pending = new ArrayList<>();
        Set<String> terms = new HashSet<>();
        for (TranslationOptions.Term term : options.terms()) {
            terms.add(term.source().trim());
        }

        int cacheHits = 0;
        for (String segment : segments) {
            if (segment.isBlank()) {
                results.putIfAbsent(segment, new TranslationBatch.TranslationItem(segment, "", "ok", ""));
                continue;
            }
            if (results.containsKey(segment)) {
                continue;
            }
            if (useCache && !terms.contains(segment)) {
                var hit = cache.get(cacheKey(segment));
                if (hit.isPresent() && "ok".equals(hit.get().status())) {
                    TranslationCache.CachedTranslation value = hit.get();
                    results.put(segment, new TranslationBatch.TranslationItem(
                            segment, value.translated(), value.status(), value.model()));
                    cacheHits++;
                    continue;
                }
            }
            if (!pending.contains(segment)) {
                pending.add(segment);
            }
        }

        TranslationBatch batch = pending.isEmpty()
                ? new TranslationBatch(List.of(), new TranslationBatch.Usage(0, 0))
                : model.translate(pending, options, progress);
        for (TranslationBatch.TranslationItem item : batch.items()) {
            results.put(item.source(), item);
            if (useCache && "ok".equals(item.status()) && !terms.contains(item.source())) {
                cache.put(cacheKey(item.source()), new TranslationCache.CachedTranslation(
                        item.translated(), item.status(), item.model()));
            }
        }

        List<String> translations = new ArrayList<>();
        List<String> statuses = new ArrayList<>();
        int reviewCount = 0;
        for (String segment : segments) {
            TranslationBatch.TranslationItem item = results.get(segment);
            if (item == null) {
                throw new TranslationToolException("Model did not return a result for segment");
            }
            translations.add(item.translated());
            statuses.add(item.status());
            if (!"ok".equals(item.status())) {
                reviewCount++;
            }
        }
        progress.emit(Map.of("phase", "translated", "total", segments.size(), "review", reviewCount));
        return new TranslationResult(
                translations,
                statuses,
                options.premium() ? "qwen3.7-plus" : options.model(),
                batch.usage(),
                cacheHits,
                reviewCount
        );
    }

    private TranslationOptions options(Map<String, Object> input) {
        List<TranslationOptions.Term> terms = new ArrayList<>();
        Object rawTerms = input.get("terms");
        if (rawTerms instanceof List<?> list) {
            for (Object raw : list) {
                if (raw instanceof List<?> pair && pair.size() >= 2) {
                    terms.add(new TranslationOptions.Term(String.valueOf(pair.get(0)), String.valueOf(pair.get(1))));
                }
            }
        }
        return new TranslationOptions(
                text(input.get("model")),
                text(input.get("fallback_model")),
                text(input.get("source_lang")),
                text(input.get("target_lang")),
                terms,
                Boolean.TRUE.equals(input.get("premium"))
        );
    }

    private List<String> strings(Object value) {
        if (!(value instanceof List<?> list) || list.stream().anyMatch(item -> !(item instanceof String))) {
            throw new TranslationToolException("segments must be an array of strings");
        }
        return list.stream().map(String.class::cast).toList();
    }

    private String text(Object value) {
        return value instanceof String string ? string : null;
    }

    private String cacheKey(String segment) {
        return segment;
    }

    public record TranslationResult(
            List<String> translations,
            List<String> statuses,
            String model,
            TranslationBatch.Usage usage,
            int cacheHits,
            int reviewCount
    ) {
        public TranslationResult {
            translations = List.copyOf(translations);
            statuses = List.copyOf(statuses);
        }

        public Map<String, Object> asMap() {
            Map<String, Object> result = new HashMap<>();
            result.put("translations", translations);
            result.put("statuses", statuses);
            result.put("model", model);
            result.put("usage", usage.asMap());
            result.put("review_count", reviewCount);
            result.put("cache_hits", cacheHits);
            return Map.copyOf(result);
        }
    }

    public static final class TranslationToolException extends RuntimeException {
        public TranslationToolException(String message) {
            super(message);
        }
    }
}
