package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class LlmChatCompleteTool extends AbstractLlmChatTool {
    public static final String ID = "llm.chat.complete";

    public LlmChatCompleteTool(LlmClient client, ObjectMapper mapper) {
        super(client, mapper, false);
    }

    @Override
    public String id() {
        return ID;
    }
}
