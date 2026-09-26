package com.zthcpa.command.tools.spi;

import com.zthcpa.command.contract.ToolKey;

import java.util.Map;

/** Executable boundary for tools implemented inside the Java runtime. */
public interface JavaTool {
    ToolKey key();

    Map<String, Object> execute(Map<String, Object> input, ProgressSink progress);
}
