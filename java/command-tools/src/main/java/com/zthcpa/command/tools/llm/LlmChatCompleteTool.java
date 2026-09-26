package com.zthcpa.command.tools.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.ToolKey;

public final class LlmChatCompleteTool extends AbstractLlmChatTool {
    public static final ToolKey KEY = new ToolKey("llm.chat.complete", 1);

    public LlmChatCompleteTool(LlmClient client, ObjectMapper mapper) {
        super(client, mapper, false);
    }

    @Override
    public ToolKey key() {
        return KEY;
    }
}
