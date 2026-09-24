package com.zthcpa.command.tools;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryTranslationCache implements TranslationCache {
    private final Map<String, CachedTranslation> values = new ConcurrentHashMap<>();

    @Override
    public Optional<CachedTranslation> get(String key) {
        return Optional.ofNullable(values.get(key));
    }

    @Override
    public void put(String key, CachedTranslation value) {
        values.put(key, value);
    }
}
