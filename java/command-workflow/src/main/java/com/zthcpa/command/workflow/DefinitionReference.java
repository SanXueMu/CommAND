package com.zthcpa.command.workflow;

import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.ToolKey;

public record DefinitionReference(DefinitionKey definition, ToolKey tool) {
    public DefinitionReference {
        if ((definition == null) == (tool == null)) {
            throw new IllegalArgumentException("A step must reference exactly one definition or tool");
        }
    }

    public static DefinitionReference definition(DefinitionKey key) {
        return new DefinitionReference(key, null);
    }

    public static DefinitionReference tool(ToolKey key) {
        return new DefinitionReference(null, key);
    }
}
