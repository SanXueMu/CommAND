package com.zthcpa.command.tools;

import java.util.Map;

/** Executable boundary for tools implemented inside the Java runtime. */
public interface JavaTool {
    String id();

    int version();

    Map<String, Object> execute(Map<String, Object> input, ProgressSink progress);
}
