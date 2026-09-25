package com.zthcpa.command.tools.spi;

import java.util.Map;

@FunctionalInterface
public interface ProgressSink {
    void emit(Map<String, Object> event);
}
