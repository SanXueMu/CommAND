package com.zthcpa.command.tools;

import java.util.Optional;

public interface TranslationCache {
    Optional<CachedTranslation> get(String key);

    void put(String key, CachedTranslation value);

    record CachedTranslation(String translated, String status, String model) { }
}
