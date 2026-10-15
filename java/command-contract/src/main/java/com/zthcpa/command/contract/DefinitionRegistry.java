package com.zthcpa.command.contract;

import java.util.List;

public interface DefinitionRegistry {
    default void register(DefinitionDocument definition) {
        throw new UnsupportedOperationException("Runtime definition registration is not supported");
    }

    DefinitionDocument get(DefinitionKey key);

    DefinitionDocument getActive(DefinitionKind kind, String id);

    List<DefinitionDocument> list(DefinitionKind kind);
}
