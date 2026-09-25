package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class LlmChatCompleteJsonTool extends AbstractLlmChatTool {
    public static final String ID = "llm.chat.complete-json";

    public LlmChatCompleteJsonTool(LlmClient client, ObjectMapper mapper) {
        super(client, mapper, true);
    }

    @Override
    public String id() {
        return ID;
    }
}
