package com.zthcpa.command.tools.llm;

public final class LlmToolException extends RuntimeException {
    public LlmToolException(String message) {
        super(message);
    }

    public LlmToolException(String message, Throwable cause) {
        super(message, cause);
    }
}
