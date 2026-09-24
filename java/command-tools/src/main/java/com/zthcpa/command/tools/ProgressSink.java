package com.zthcpa.command.tools;

import java.util.Map;

@FunctionalInterface
public interface ProgressSink {
    void emit(Map<String, Object> event);
}
