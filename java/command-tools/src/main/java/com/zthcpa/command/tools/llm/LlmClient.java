package com.zthcpa.command.tools.llm;

public interface LlmClient {
    LlmResponse complete(LlmRequest request);
}
