package com.zthcpa.command.tools;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TextLlmTranslateToolTest {
    @Test
    void preservesInputAlignmentAndUsesOnlySuccessfulCacheEntries() {
        FakeCache cache = new FakeCache();
        cache.values.put("cached", new TranslationCache.CachedTranslation("已缓存", "ok", "cache-model"));
        cache.values.put("review", new TranslationCache.CachedTranslation("旧译文", "review", "cache-model"));
        FakeModel model = new FakeModel();
        TextLlmTranslateTool tool = new TextLlmTranslateTool(model, cache);

        TextLlmTranslateTool.TranslationResult result = tool.execute(Map.of(
                "segments", List.of("cached", "review", "", "review", "term"),
                "terms", List.of(List.of("term", "术语")),
                "use_cache", true
        ), event -> { });

        assertEquals(List.of("已缓存", "翻译-review", "", "翻译-review", "翻译-term"), result.translations());
        assertEquals(List.of("ok", "ok", "ok", "ok", "ok"), result.statuses());
        assertEquals(1, result.cacheHits());
        assertEquals(List.of("review", "term"), model.segments);
        assertEquals(1, cache.puts.size());
        assertEquals("翻译-review", cache.puts.get("review").translated());
    }

    @Test
    void emitsTranslatedSummaryAndReturnsStructuredUsage() {
        FakeCache cache = new FakeCache();
        FakeModel model = new FakeModel();
        TextLlmTranslateTool tool = new TextLlmTranslateTool(model, cache);
        List<Map<String, Object>> events = new ArrayList<>();

        TextLlmTranslateTool.TranslationResult result = tool.execute(
                Map.of("segments", List.of("one"), "premium", true), events::add);

        assertEquals("qwen3.7-plus", result.model());
        assertEquals(new TranslationBatch.Usage(11, 7), result.usage());
        assertEquals(Map.of("phase", "translated", "total", 1, "review", 0), events.get(1));
    }

    private static final class FakeModel implements TranslationModel {
        private List<String> segments = List.of();

        @Override
        public TranslationBatch translate(List<String> segments, TranslationOptions options, ProgressSink progress) {
            this.segments = List.copyOf(segments);
            progress.emit(Map.of("phase", "translating", "total", segments.size()));
            return new TranslationBatch(
                    segments.stream()
                            .map(segment -> new TranslationBatch.TranslationItem(
                                    segment, "翻译-" + segment, "ok", options.model()))
                            .toList(),
                    new TranslationBatch.Usage(11, 7)
            );
        }
    }

    private static final class FakeCache implements TranslationCache {
        private final Map<String, CachedTranslation> values = new HashMap<>();
        private final Map<String, CachedTranslation> puts = new HashMap<>();

        @Override
        public Optional<CachedTranslation> get(String key) {
            return Optional.ofNullable(values.get(key));
        }

        @Override
        public void put(String key, CachedTranslation value) {
            puts.put(key, value);
        }
    }
}
