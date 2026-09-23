package com.zthcpa.command.contract;

import java.util.List;

public interface DefinitionRepository {
    void saveIfAbsent(DefinitionDocument definition);

    List<DefinitionDocument> list();
}
