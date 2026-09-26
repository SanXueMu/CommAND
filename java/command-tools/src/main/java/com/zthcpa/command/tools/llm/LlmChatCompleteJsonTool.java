package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.ToolKey;

public final class LlmChatCompleteJsonTool extends AbstractLlmChatTool {
    public static final ToolKey KEY = new ToolKey("llm.chat.complete-json", 1);

    public LlmChatCompleteJsonTool(LlmClient client, ObjectMapper mapper) {
        super(client, mapper, true);
    }

    @Override
    public ToolKey key() {
        return KEY;
    }
}
