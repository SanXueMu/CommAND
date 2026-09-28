package com.zthcpa.command.tools.text;

import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.tools.spi.JavaTool;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Reusable source/translation fidelity checks migrated from text.verify.fidelity. */
public final class VerifyFidelityTool implements JavaTool {
    public static final ToolKey KEY = new ToolKey("text.verify.fidelity", 1);
    private static final Pattern DIGITS = Pattern.compile("\\d+");
    private static final Pattern PLACEHOLDER = Pattern.compile("\\[\\[DATE_\\d+\\]\\]");
    private static final Pattern HAS_LETTER = Pattern.compile("[A-Za-z\\u4e00-\\u9fff]");
    private static final Pattern EN_WORD = Pattern.compile("[A-Za-z]{2,}");
    private static final Pattern CJK = Pattern.compile("[\\u4e00-\\u9fff]");

    @Override
    public ToolKey key() {
        return KEY;
    }

    @Override
    public Map<String, Object> execute(Map<String, Object> input, ProgressSink progress) {
        if (!(input.get("sources") instanceof List<?> sources)
                || !(input.get("translations") instanceof List<?> translations)) {
            throw new IllegalArgumentException("sources and translations must be arrays");
        }
        if (sources.size() != translations.size()) {
            throw new IllegalArgumentException("sources/translations length mismatch: "
                    + sources.size() + " vs " + translations.size());
        }
        List<String> statuses = new ArrayList<>();
        List<String> reasons = new ArrayList<>();
        int okCount = 0;
        for (int i = 0; i < sources.size(); i++) {
            if (!(sources.get(i) instanceof String source) || !(translations.get(i) instanceof String translation)) {
                throw new IllegalArgumentException("sources and translations must contain strings");
            }
            String reason = verify(source, translation);
            statuses.add(reason.isEmpty() ? "ok" : "review");
            reasons.add(reason);
            if (reason.isEmpty()) okCount++;
        }
        progress.emit(Map.of("phase", "verified", "total", sources.size(), "ok", okCount));
        return Map.of("statuses", statuses, "reasons", reasons, "ok_count", okCount, "total", sources.size());
    }

    private String verify(String source, String translation) {
        String src = source.trim();
        String dst = translation.trim();
        if (src.isEmpty()) return "";
        if (dst.isEmpty()) return "empty";
        Matcher placeholders = PLACEHOLDER.matcher(src);
        while (placeholders.find() && !dst.contains(placeholders.group())) {
            return "missing_placeholder:" + placeholders.group();
        }
        String sourceWithoutPlaceholders = PLACEHOLDER.matcher(src).replaceAll("");
        Matcher digits = DIGITS.matcher(sourceWithoutPlaceholders);
        while (digits.find() && !dst.contains(digits.group())) {
            return "missing_number:" + digits.group();
        }
        if (!HAS_LETTER.matcher(src).find() && !dst.equals(src)) return "not_identical";
        List<String> sourceWords = findAll(EN_WORD, src);
        if (sourceWords.size() >= 2 && !CJK.matcher(dst).find()
                && findAll(EN_WORD, dst).size() >= Math.max(2, (int) (sourceWords.size() * 0.6))) {
            return "untranslated";
        }
        if (src.length() >= 60 && dst.length() < src.length() * 0.3) return "truncated";
        return "";
    }

    private List<String> findAll(Pattern pattern, String value) {
        List<String> matches = new ArrayList<>();
        Matcher matcher = pattern.matcher(value);
        while (matcher.find()) matches.add(matcher.group());
        return matches;
    }
}
