package com.zthcpa.command.contract;

import java.util.List;

public interface DefinitionRegistry {
    DefinitionDocument get(DefinitionKey key);

    DefinitionDocument getActive(DefinitionKind kind, String id);

    List<DefinitionDocument> list(DefinitionKind kind);
}
