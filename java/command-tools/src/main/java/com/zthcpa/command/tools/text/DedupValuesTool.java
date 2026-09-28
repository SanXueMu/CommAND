package com.zthcpa.command.tools.text;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Date-normalizing value deduplication migrated from text.dedup.values. */
public final class DedupValuesTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("text.dedup.values", 1);
    private static final Pattern DATE = Pattern.compile("\\d{4}[-/.]\\d{1,2}[-/.]\\d{1,2}|\\d{1,2}[-/]\\d{1,2}[-/]\\d{4}");

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        if (!(input.get("segments") instanceof List<?> raw)) {
            throw new IllegalArgumentException("segments must be an array");
        }
        List<String> unique = new ArrayList<>();
        Map<String, Integer> firstSeen = new LinkedHashMap<>();
        List<Integer> indexMap = new ArrayList<>();
        List<Map<String, String>> dateMaps = new ArrayList<>();
        for (Object value : raw) {
            if (!(value instanceof String segment)) throw new IllegalArgumentException("segments must contain strings");
            Normalized normalized = normalize(segment);
            int index = firstSeen.computeIfAbsent(normalized.text(), ignored -> {
                unique.add(normalized.text());
                return unique.size() - 1;
            });
            indexMap.add(index);
            dateMaps.add(normalized.dates());
        }
        progress.emit(Map.of("phase", "deduped", "input", raw.size(), "unique", unique.size()));
        return Map.of("unique", unique, "index_map", indexMap, "date_maps", dateMaps);
    }

    private Normalized normalize(String text) {
        Matcher matcher = DATE.matcher(text);
        StringBuffer normalized = new StringBuffer();
        Map<String, String> dates = new LinkedHashMap<>();
        while (matcher.find()) {
            String placeholder = "[[DATE_" + (dates.size() + 1) + "]]";
            dates.put(placeholder, matcher.group());
            matcher.appendReplacement(normalized, Matcher.quoteReplacement(placeholder));
        }
        matcher.appendTail(normalized);
        return new Normalized(normalized.toString(), dates);
    }

    private record Normalized(String text, Map<String, String> dates) {
    }
}
